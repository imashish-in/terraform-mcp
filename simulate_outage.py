#!/usr/bin/env python3
"""
Simulate a production topology in local Floci:
1. Creates a VPC and Subnet
2. Creates an Order Processing Security Group
3. Attaches 3 active Elastic Network Interfaces (simulating live ECS Fargate microservice tasks)
4. Generates a matching `live_plan_case_a.json` Terraform plan for immediate testing
"""

import json
from pathlib import Path
import boto3

def main():
    endpoint_url = "http://localhost:4566"
    region_name = "us-east-1"
    
    print(f"[*] Connecting to Floci emulator at {endpoint_url}...")
    ec2 = boto3.client(
        "ec2",
        endpoint_url=endpoint_url,
        region_name=region_name,
        aws_access_key_id="test",
        aws_secret_access_key="test",
    )

    # 1. Create VPC & Subnet
    print("[1/3] Creating simulated VPC & Subnet in Floci...")
    vpc = ec2.create_vpc(CidrBlock="10.0.0.0/16")
    vpc_id = vpc["Vpc"]["VpcId"]
    
    subnet = ec2.create_subnet(VpcId=vpc_id, CidrBlock="10.0.1.0/24")
    subnet_id = subnet["Subnet"]["SubnetId"]
    print(f"      VPC: {vpc_id} | Subnet: {subnet_id}")

    # 2. Create Security Group for Order Processing Service
    print("[2/3] Creating Order Processing Security Group...")
    sg = ec2.create_security_group(
        GroupName="order-service-sg",
        Description="Order Processing Microservice SG",
        VpcId=vpc_id,
    )
    sg_id = sg["GroupId"]
    print(f"      Created Security Group: {sg_id}")

    # 3. Simulate active ECS Fargate tasks bound to this Security Group
    print("[3/3] Simulating live active ECS Fargate task bindings (ENIs)...")
    for i in range(1, 4):
        eni = ec2.create_network_interface(
            SubnetId=subnet_id,
            Groups=[sg_id],
            Description=f"arn:aws:ecs:us-east-1:123456789012:task/order-service/task-{i} production-traffic",
        )
        eni_id = eni["NetworkInterface"]["NetworkInterfaceId"]
        ip = eni["NetworkInterface"].get("PrivateIpAddress", "10.0.1.x")
        print(f"      -> Attached Live ENI: {eni_id} (IP: {ip}, Task: task-{i})")

    # 4. Generate matching test plan
    fixture_path = Path("tests/fixtures/case_a_port_revocation.json")
    if fixture_path.exists():
        template = json.loads(fixture_path.read_text(encoding="utf-8"))
        template["resource_changes"][0]["change"]["before"]["id"] = sg_id
        template["resource_changes"][0]["change"]["after"]["id"] = sg_id
        
        output_plan = Path("live_plan_case_a.json")
        output_plan.write_text(json.dumps(template, indent=2), encoding="utf-8")
        print(f"\n[+] Generated matching test plan: {output_plan}")

    print("\n" + "=" * 70)
    print(f"SUCCESS: Simulated production microservice is live in Floci!")
    print(f"Target Security Group ID: {sg_id}")
    print("=" * 70)
    print("\nRun the pre-merge gate now to see it block the PR:")
    print("terraform-mcp evaluate --plan live_plan_case_a.json --endpoint-url http://localhost:4566 --no-fail")

if __name__ == "__main__":
    main()
