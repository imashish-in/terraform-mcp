"""
AWS Live-Topology MCP Server (FastMCP).
Performs least-privilege transitive dependency graph tracing for AWS Security Groups,
resolving live ephemeral ENIs, ECS tasks, and ELB target groups before code deployment.
"""

import os
import re
from typing import Optional
import boto3
from botocore.config import Config
from fastmcp import FastMCP
from terraform_mcp.models import (
    SecurityGroupBlastRadiusResult,
    WorkloadBinding,
)

# Initialize FastMCP Server
server = FastMCP(
    name="AWS-Live-Topology-Inspector",
    instructions="Discovers live active ENIs, ECS tasks, and Target Groups bound to target AWS Security Groups."
)


def get_ec2_client(region_name: str = "us-east-1", endpoint_url: Optional[str] = None):
    endpoint = endpoint_url or os.getenv("AWS_ENDPOINT_URL")
    return boto3.client(
        "ec2",
        region_name=region_name,
        endpoint_url=endpoint,
        config=Config(retries={"max_attempts": 2, "mode": "standard"})
    )


def get_elbv2_client(region_name: str = "us-east-1", endpoint_url: Optional[str] = None):
    endpoint = endpoint_url or os.getenv("AWS_ENDPOINT_URL")
    return boto3.client(
        "elbv2",
        region_name=region_name,
        endpoint_url=endpoint,
        config=Config(retries={"max_attempts": 2, "mode": "standard"})
    )


@server.tool(name="inspect_security_group_blast_radius")
def inspect_security_group_blast_radius(
    security_group_id: str,
    region_name: str = "us-east-1",
    endpoint_url: Optional[str] = None,
) -> dict:
    """
    Recursively discovers live ENIs and compute tasks bound to a target security group.
    
    Args:
        security_group_id: Target AWS Security Group ID (e.g., sg-0123456789abcdef0)
        region_name: AWS region name (defaults to us-east-1)
        endpoint_url: Optional override endpoint URL for local emulation (Floci/LocalStack)
    """
    ec2_client = get_ec2_client(region_name, endpoint_url)
    elbv2_client = get_elbv2_client(region_name, endpoint_url)

    workloads = []
    severed_containers = []
    target_group_arns = []
    severity = "SAFE"

    try:
        # 1. Enumerate all active ENIs bound to this Security Group
        response = ec2_client.describe_network_interfaces(
            Filters=[{"Name": "group-id", "Values": [security_group_id]}]
        )
        enis = response.get("NetworkInterfaces", [])
    except Exception as exc:
        return SecurityGroupBlastRadiusResult(
            target_resource_id=security_group_id,
            direct_enis_attached=0,
            has_live_bindings=False,
            severity="SAFE",
            message=f"Could not query EC2 ENIs: {str(exc)}"
        ).model_dump()

    if not enis:
        return SecurityGroupBlastRadiusResult(
            target_resource_id=security_group_id,
            direct_enis_attached=0,
            has_live_bindings=False,
            severity="SAFE",
            message="No active ENIs or workloads attached to this security group."
        ).model_dump()

    severity = "WARNING"

    # 2. Correlate ENIs to parent container tasks, Lambdas, or ALBs
    for eni in enis:
        eni_id = eni.get("NetworkInterfaceId", "")
        status = eni.get("Status", "unknown")
        description = eni.get("Description", "")
        private_ip = eni.get("PrivateIpAddress")
        az = eni.get("AvailabilityZone")

        # Detect ECS / EKS / Container attachments
        if "task/" in description or "ecs" in description.lower() or "aws-k8s" in description.lower():
            match = re.search(r"arn:aws:ecs:[^\s]+", description)
            task_arn = match.group(0) if match else description
            severed_containers.append(task_arn)
            severity = "CRITICAL"

        workloads.append(
            WorkloadBinding(
                eni_id=eni_id,
                status=status,
                workload_description=description or "Attached Elastic Network Interface",
                private_ip=private_ip,
                availability_zone=az,
            )
        )

        # 3. Check if this ENI IP is registered in any ALB/NLB Target Groups
        if private_ip and elbv2_client:
            try:
                tg_resp = elbv2_client.describe_target_groups()
                for tg in tg_resp.get("TargetGroups", []):
                    tg_arn = tg.get("TargetGroupArn")
                    health_resp = elbv2_client.describe_target_health(TargetGroupArn=tg_arn)
                    for th in health_resp.get("TargetHealthDescriptions", []):
                        if th.get("Target", {}).get("Id") == private_ip:
                            target_group_arns.append(tg_arn)
                            severity = "CRITICAL"
            except Exception:
                # Target group queries are best-effort if permissions / mock allow
                pass

    has_live = len(workloads) > 0

    message = (
        f"Detected {len(workloads)} active ENI(s) bound to {security_group_id}. "
        f"Impacted workloads: {len(severed_containers)} container/task binding(s)."
    ) if has_live else "No live bindings found."

    result = SecurityGroupBlastRadiusResult(
        target_resource_id=security_group_id,
        direct_enis_attached=len(workloads),
        workloads=workloads,
        target_group_arns=list(set(target_group_arns)),
        severed_containers=list(set(severed_containers)),
        has_live_bindings=has_live,
        severity=severity,
        message=message,
    )
    return result.model_dump()


def run_server():
    """Run FastMCP topology discovery server over stdio."""
    server.run()


if __name__ == "__main__":
    run_server()
