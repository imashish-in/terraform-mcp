import asyncio
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path
import boto3
from moto import mock_aws

from terraform_mcp.models import GateVerdict
from terraform_mcp.orchestrator import MeshOrchestrator

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def test_empirical_benchmark_suite():
    """
    Empirical benchmark reproducing the paper's evaluation testbed:
    - Verifies latency (< 250ms end-to-end)
    - Verifies Case A, Case B, Case C detection accuracy
    """
    with mock_aws():
        ec2 = boto3.client("ec2", region_name="us-east-1")
        cw = boto3.client("cloudwatch", region_name="us-east-1")

        # Setup Case A Environment (VPC + SG + 18 simulated live ECS ENIs)
        vpc = ec2.create_vpc(CidrBlock="10.0.0.0/16")
        subnet = ec2.create_subnet(VpcId=vpc["Vpc"]["VpcId"], CidrBlock="10.0.1.0/24")
        sg = ec2.create_security_group(
            GroupName="order-service-sg",
            Description="Order SG",
            VpcId=vpc["Vpc"]["VpcId"],
        )
        sg_id = sg["GroupId"]

        # Provision 18 live ENIs bound to this SG (as evaluated in Case A of the paper)
        for i in range(18):
            ec2.create_network_interface(
                SubnetId=subnet["Subnet"]["SubnetId"],
                Groups=[sg_id],
                Description=f"arn:aws:ecs:us-east-1:123456789012:task/order-service/task-{i+1}",
            )

        # Setup Case B Environment (Instance with P99 CPU = 12.4%)
        instance_id = "i-0987654321fedcba0"
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

        # Read plan files
        plan_a = (FIXTURES_DIR / "case_a_port_revocation.json").read_text(encoding="utf-8").replace("sg-0a1b2c3d4e5f60718", sg_id)
        plan_b = (FIXTURES_DIR / "case_b_compute_upsize.json").read_text(encoding="utf-8")
        plan_c = (FIXTURES_DIR / "case_c_route_modification.json").read_text(encoding="utf-8")

        orchestrator = MeshOrchestrator(region_name="us-east-1")

        # Run Benchmark Iterations to compute latency distribution
        latencies = []
        for _ in range(10):
            t0 = time.perf_counter()
            rep_a = asyncio.run(orchestrator.evaluate_plan(plan_a))
            lat = (time.perf_counter() - t0) * 1000.0
            latencies.append(lat)

        mean_latency = statistics.mean(latencies)
        std_dev = statistics.stdev(latencies) if len(latencies) > 1 else 0.0

        print(f"\n[BENCHMARK] Mean Latency: {mean_latency:.2f} ms (+/- {std_dev:.2f} ms)")

        # Assertions
        # 1. Sub-second latency (< 250 ms)
        assert mean_latency < 250.0, f"Latency {mean_latency}ms exceeded 250ms target"

        # 2. Case A Detection: Blocked with 18 severed containers
        rep_a = asyncio.run(orchestrator.evaluate_plan(plan_a))
        assert rep_a.overall_verdict == GateVerdict.BLOCK_PR_CRITICAL_BLAST_RADIUS
        assert rep_a.topology_results[0].direct_enis_attached == 18
        assert len(rep_a.topology_results[0].severed_containers) == 18

        # 3. Case B Detection: Blocked with structural compute waste
        rep_b = asyncio.run(orchestrator.evaluate_plan(plan_b))
        assert rep_b.overall_verdict == GateVerdict.BLOCK_PR_FINOPS_WASTE
        assert rep_b.finops_results[0].is_overprovisioned is True
        assert rep_b.finops_results[0].observed_peak_cpu_percent == 12.4

        # 4. Case C Detection: Evaluated successfully
        rep_c = asyncio.run(orchestrator.evaluate_plan(plan_c))
        assert rep_c.overall_verdict in (GateVerdict.APPROVED, GateVerdict.WARNING_FINOPS_EGRESS)
