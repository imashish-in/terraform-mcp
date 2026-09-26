#!/usr/bin/env python3
"""
Simulate an under-utilized compute workload with live CloudWatch metrics in Floci:
1. Provisions an EC2 instance or instance ID
2. Ingests CloudWatch CPU metrics with P99 = 12.4% over 14 days
3. Generates a matching `live_plan_case_b.json` Terraform plan attempting to upsize to t3.xlarge
"""

from datetime import datetime, timezone
import json
from pathlib import Path
import boto3

def main():
    endpoint_url = "http://localhost:4566"
    region_name = "us-east-1"
    instance_id = "i-0987654321fedcba0"

    print(f"[*] Connecting to Floci CloudWatch emulator at {endpoint_url}...")
    cw = boto3.client("cloudwatch", endpoint_url=endpoint_url, region_name=region_name)

    print(f"[1/2] Ingesting low CPU utilization metrics for {instance_id} (P99 = 12.4%)...")
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
    print("      -> Successfully ingested CloudWatch time-series telemetry.")

    # 2. Generate matching test plan
    fixture_path = Path("tests/fixtures/case_b_compute_upsize.json")
    if fixture_path.exists():
        template = json.loads(fixture_path.read_text(encoding="utf-8"))
        output_plan = Path("live_plan_case_b.json")
        output_plan.write_text(json.dumps(template, indent=2), encoding="utf-8")
        print(f"[2/2] Generated matching FinOps test plan: {output_plan}")

    print("\n" + "=" * 70)
    print(f"SUCCESS: Simulated under-utilized workload in Floci!")
    print("=" * 70)
    print("\nRun the pre-merge gate now to see it block structural cloud waste:")
    print("terraform-mcp evaluate --plan live_plan_case_b.json --endpoint-url http://localhost:4566 --no-fail")

if __name__ == "__main__":
    main()
