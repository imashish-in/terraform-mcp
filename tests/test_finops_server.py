from datetime import datetime, timezone
import boto3
from moto import mock_aws
from terraform_mcp.finops_server import inspect_resource_cost_efficiency


def test_finops_inspector_overprovisioned_compute():
    with mock_aws():
        cw = boto3.client("cloudwatch", region_name="us-east-1")
        instance_id = "i-0987654321fedcba0"

        # Ingest low CPU utilization metrics (P99 = 12.4%)
        now = datetime.now(timezone.utc)
        cw.put_metric_data(
            Namespace="AWS/EC2",
            MetricData=[
                {
                    "MetricName": "CPUUtilization",
                    "Dimensions": [{"Name": "InstanceId", "Value": instance_id}],
                    "Timestamp": now,
                    "Value": 12.4,
                    "Unit": "Percent",
                }
            ],
        )

        result = inspect_resource_cost_efficiency(
            resource_id=instance_id,
            resource_type="ec2_or_ecs",
            current_type="t3.medium",
            proposed_new_type="t3.xlarge",
            lookback_days=14,
            region_name="us-east-1",
        )

        assert result["resource_id"] == instance_id
        assert result["observed_peak_cpu_percent"] == 12.4
        assert result["is_overprovisioned"] is True
        assert result["projected_monthly_compute_waste_usd"] > 0
        assert result["finops_verdict"] == "BLOCK_PR_FINOPS_WASTE"
        assert len(result["recommendations"]) > 0


def test_finops_inspector_justified_compute():
    with mock_aws():
        cw = boto3.client("cloudwatch", region_name="us-east-1")
        instance_id = "i-01122334455667788"

        # Ingest high CPU utilization metrics (P99 = 88.5%)
        now = datetime.now(timezone.utc)
        cw.put_metric_data(
            Namespace="AWS/EC2",
            MetricData=[
                {
                    "MetricName": "CPUUtilization",
                    "Dimensions": [{"Name": "InstanceId", "Value": instance_id}],
                    "Timestamp": now,
                    "Value": 88.5,
                    "Unit": "Percent",
                }
            ],
        )

        result = inspect_resource_cost_efficiency(
            resource_id=instance_id,
            resource_type="ec2_or_ecs",
            current_type="t3.medium",
            proposed_new_type="t3.xlarge",
            lookback_days=14,
            region_name="us-east-1",
        )

        assert result["resource_id"] == instance_id
        assert result["observed_peak_cpu_percent"] == 88.5
        assert result["is_overprovisioned"] is False
        assert result["finops_verdict"] == "APPROVED"
