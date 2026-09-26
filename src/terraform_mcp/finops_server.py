"""
AWS FinOps Telemetry MCP Server (FastMCP).
Samples CloudWatch utilization metrics and network egress telemetry to proactively
detect over-provisioned compute and cross-AZ data leaks prior to code merge.
"""

from datetime import datetime, timedelta, timezone
import os
from typing import Dict, List, Optional
import boto3
from botocore.config import Config
from fastmcp import FastMCP
from terraform_mcp.models import FinOpsCostEfficiencyResult

# Initialize FastMCP Server
server = FastMCP(
    name="AWS-FinOps-Cost-Inspector",
    instructions="Audits CloudWatch P99 CPU metrics and data-egress telemetry to detect structural cloud cost waste."
)

# Standard hourly on-demand AWS baseline rates (USD)
INSTANCE_HOURLY_PRICING: Dict[str, float] = {
    "t3.nano": 0.0052,
    "t3.micro": 0.0104,
    "t3.small": 0.0208,
    "t3.medium": 0.0416,
    "t3.large": 0.0832,
    "t3.xlarge": 0.1664,
    "t3.2xlarge": 0.3328,
    "m5.large": 0.0960,
    "m5.xlarge": 0.1920,
    "m5.2xlarge": 0.3840,
    "c5.large": 0.0850,
    "c5.xlarge": 0.1700,
    "c5.2xlarge": 0.3400,
    "r5.large": 0.1260,
    "r5.xlarge": 0.2520,
}

HOURS_PER_MONTH = 730.0
CROSS_AZ_EGRESS_RATE_PER_GB = 0.01  # $0.01 per GB in each direction


def get_cloudwatch_client(region_name: str = "us-east-1", endpoint_url: Optional[str] = None):
    endpoint = endpoint_url or os.getenv("AWS_ENDPOINT_URL")
    return boto3.client(
        "cloudwatch",
        region_name=region_name,
        endpoint_url=endpoint,
        config=Config(retries={"max_attempts": 2, "mode": "standard"})
    )


def get_ec2_client(region_name: str = "us-east-1", endpoint_url: Optional[str] = None):
    endpoint = endpoint_url or os.getenv("AWS_ENDPOINT_URL")
    return boto3.client(
        "ec2",
        region_name=region_name,
        endpoint_url=endpoint,
        config=Config(retries={"max_attempts": 2, "mode": "standard"})
    )


@server.tool(name="inspect_resource_cost_efficiency")
def inspect_resource_cost_efficiency(
    resource_id: str,
    resource_type: str = "ec2_or_ecs",
    current_type: Optional[str] = None,
    proposed_new_type: Optional[str] = None,
    lookback_days: int = 14,
    region_name: str = "us-east-1",
    endpoint_url: Optional[str] = None,
) -> dict:
    """
    Samples CloudWatch metrics to detect over-provisioned compute and cross-AZ egress leaks.
    
    Args:
        resource_id: Resource ID (e.g., i-0123456789abcdef0, ecs-service-name, or rtb-0123)
        resource_type: Type of resource (ec2_or_ecs, rds, route_table)
        current_type: Current instance/task size (e.g., t3.medium)
        proposed_new_type: Proposed target instance/task size (e.g., t3.xlarge)
        lookback_days: Number of historical days to evaluate (default 14)
        region_name: AWS region name
        endpoint_url: Optional override endpoint URL for local emulation
    """
    # 1. Dynamically discover live current instance type from live AWS EC2 if not provided in plan
    if not current_type and resource_type in ("ec2_or_ecs", "aws_instance", "aws_launch_template"):
        try:
            ec2_client = get_ec2_client(region_name, endpoint_url)
            if resource_id.startswith("i-") and len(resource_id) > 10:
                desc = ec2_client.describe_instances(InstanceIds=[resource_id])
                for r in desc.get("Reservations", []):
                    for inst in r.get("Instances", []):
                        current_type = inst.get("InstanceType")
            if not current_type:
                desc = ec2_client.describe_instances(Filters=[{"Name": "tag:Name", "Values": [resource_id]}])
                for r in desc.get("Reservations", []):
                    for inst in r.get("Instances", []):
                        current_type = inst.get("InstanceType")
        except Exception:
            pass

    cw_client = get_cloudwatch_client(region_name, endpoint_url)
    now_utc = datetime.now(timezone.utc)
    end_time = now_utc + timedelta(hours=1)
    start_time = now_utc - timedelta(days=lookback_days)

    peak_cpu = 0.0
    total_bytes_out = 0.0

    namespace = "AWS/EC2" if resource_type in ("ec2_or_ecs", "aws_instance", "aws_launch_template") else "AWS/ECS"
    dimension_name = "InstanceId" if namespace == "AWS/EC2" else "ServiceName"

    # 1. Query CloudWatch for CPU Utilization metrics
    try:
        stats_resp = cw_client.get_metric_statistics(
            Namespace=namespace,
            MetricName="CPUUtilization",
            Dimensions=[{"Name": dimension_name, "Value": resource_id}],
            StartTime=start_time,
            EndTime=end_time,
            Period=3600,
            Statistics=["Average", "Maximum"],
            ExtendedStatistics=["p99"],
        )
        datapoints = stats_resp.get("Datapoints", [])
        if not datapoints:
            try:
                stats_resp = cw_client.get_metric_statistics(
                    Namespace="Custom/EC2" if namespace == "AWS/EC2" else "Custom/ECS",
                    MetricName="CPUUtilization",
                    Dimensions=[{"Name": dimension_name, "Value": resource_id}],
                    StartTime=start_time,
                    EndTime=end_time,
                    Period=3600,
                    Statistics=["Average", "Maximum"],
                    ExtendedStatistics=["p99"],
                )
                datapoints = stats_resp.get("Datapoints", [])
            except Exception:
                pass
        if datapoints:
            for dp in datapoints:
                val = dp.get("ExtendedStatistics", {}).get("p99")
                if val is None:
                    val = dp.get("Maximum")
                if val is None:
                    val = dp.get("Average")
                if val is not None and float(val) > peak_cpu:
                    peak_cpu = float(val)

        # Query NetworkOut
        net_resp = cw_client.get_metric_statistics(
            Namespace="AWS/EC2",
            MetricName="NetworkOut",
            Dimensions=[{"Name": "InstanceId", "Value": resource_id}],
            StartTime=start_time,
            EndTime=end_time,
            Period=86400,
            Statistics=["Sum"],
        )
        for dp in net_resp.get("Datapoints", []):
            if "Sum" in dp:
                total_bytes_out += float(dp["Sum"])

    except Exception:
        pass

    total_gb_transferred = total_bytes_out / (1024 ** 3)

    # 2. Compute cost differentials
    curr_rate = INSTANCE_HOURLY_PRICING.get(current_type or "", 0.0)
    new_rate = INSTANCE_HOURLY_PRICING.get(proposed_new_type or "", curr_rate)

    cost_delta_monthly = (new_rate - curr_rate) * HOURS_PER_MONTH if (curr_rate and new_rate) else 0.0

    # Algorithm 2: Usage-Correlated Waste Heuristic
    # Threshold theta_cpu = 20%
    is_overprovisioned = False
    recommendations: List[str] = []
    verdict = "APPROVED"

    if proposed_new_type and current_type and new_rate > curr_rate:
        if 0.0 < peak_cpu < 20.0:
            is_overprovisioned = True
            verdict = "BLOCK_PR_FINOPS_WASTE"
            recommendations.append(
                f"Workload {resource_id} has observed a peak P99 CPU of only {peak_cpu:.1f}% over {lookback_days} days. "
                f"Upscaling from {current_type} to {proposed_new_type} introduces +${cost_delta_monthly:.2f}/mo in structural waste. "
                f"Reject resize or implement autoscaling."
            )
        elif peak_cpu == 0.0:
            recommendations.append(
                f"No live CloudWatch CPU metrics detected for {resource_id}. Proceed with telemetry validation."
            )

    # Cross-AZ Egress Check
    projected_network_waste = 0.0
    if total_gb_transferred > 500:
        # Scale to 30 days
        monthly_gb = (total_gb_transferred / max(lookback_days, 1)) * 30.0
        projected_network_waste = monthly_gb * CROSS_AZ_EGRESS_RATE_PER_GB
        recommendations.append(
            f"Detected {monthly_gb:.1f} GB/mo egress. Without VPC Endpoints or colocation, "
            f"this generates ~${projected_network_waste:.2f}/mo in Cross-AZ data transfer fees."
        )
        if verdict == "APPROVED":
            verdict = "WARNING_FINOPS_EGRESS"

    result = FinOpsCostEfficiencyResult(
        resource_id=resource_id,
        resource_type=resource_type,
        current_instance_type=current_type,
        proposed_new_type=proposed_new_type,
        observed_peak_cpu_percent=round(peak_cpu, 2),
        total_gb_transferred=round(total_gb_transferred, 2),
        is_overprovisioned=is_overprovisioned,
        projected_monthly_compute_waste_usd=round(cost_delta_monthly, 2) if is_overprovisioned else 0.0,
        projected_monthly_network_waste_usd=round(projected_network_waste, 2),
        recommendations=recommendations,
        finops_verdict=verdict,
    )
    return result.model_dump()


def run_server():
    """Run FastMCP FinOps discovery server over stdio."""
    server.run()


if __name__ == "__main__":
    run_server()
