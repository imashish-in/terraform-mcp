import asyncio
from datetime import datetime, timezone
from pathlib import Path
import boto3
from moto import mock_aws

from terraform_mcp.models import GateVerdict
from terraform_mcp.orchestrator import MeshOrchestrator

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def test_orchestrator_blocks_case_a_reliability():
    with mock_aws():
        ec2 = boto3.client("ec2", region_name="us-east-1")
        vpc = ec2.create_vpc(CidrBlock="10.0.0.0/16")
        subnet = ec2.create_subnet(VpcId=vpc["Vpc"]["VpcId"], CidrBlock="10.0.1.0/24")

        # Create target SG
        sg = ec2.create_security_group(
            GroupName="order-service-sg",
            Description="Order SG",
            VpcId=vpc["Vpc"]["VpcId"],
        )
        sg_id = sg["GroupId"]

        # Attach live ENI
        ec2.create_network_interface(
            SubnetId=subnet["Subnet"]["SubnetId"],
            Groups=[sg_id],
            Description="arn:aws:ecs:us-east-1:123456789012:task/orders/task-18-production",
        )

        plan_json = (FIXTURES_DIR / "case_a_port_revocation.json").read_text(encoding="utf-8")
        # Substitute SG ID
        plan_json = plan_json.replace("sg-0a1b2c3d4e5f60718", sg_id)

        orchestrator = MeshOrchestrator(region_name="us-east-1")
        report = asyncio.run(orchestrator.evaluate_plan(plan_json))

        assert report.overall_verdict == GateVerdict.BLOCK_PR_CRITICAL_BLAST_RADIUS
        assert len(report.topology_results) == 1
        assert report.topology_results[0].severity == "CRITICAL"
        assert len(report.topology_results[0].severed_containers) == 1
        assert "### :fire: IaC Pre-Merge Gate: BLOCKED" in report.summary_markdown


def test_orchestrator_blocks_case_b_finops():
    with mock_aws():
        cw = boto3.client("cloudwatch", region_name="us-east-1")
        instance_id = "i-0987654321fedcba0"

        # Low CPU utilization
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

        plan_json = (FIXTURES_DIR / "case_b_compute_upsize.json").read_text(encoding="utf-8")

        orchestrator = MeshOrchestrator(region_name="us-east-1")
        report = asyncio.run(orchestrator.evaluate_plan(plan_json))

        assert report.overall_verdict == GateVerdict.BLOCK_PR_FINOPS_WASTE
        assert len(report.finops_results) == 1
        assert report.finops_results[0].is_overprovisioned is True
        assert "### :no_entry_sign: IaC Pre-Merge Gate: BLOCKED" in report.summary_markdown
