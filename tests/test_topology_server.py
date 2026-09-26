import boto3
from moto import mock_aws
from terraform_mcp.topology_server import inspect_security_group_blast_radius


@mock_aws
def test_topology_inspector_empty_sg():
    ec2 = boto3.client("ec2", region_name="us-east-1")
    vpc = ec2.create_vpc(CidrBlock="10.0.0.0/16")
    sg = ec2.create_security_group(
        GroupName="empty-sg",
        Description="Empty Security Group",
        VpcId=vpc["Vpc"]["VpcId"],
    )
    sg_id = sg["GroupId"]

    result = inspect_security_group_blast_radius(security_group_id=sg_id, region_name="us-east-1")

    assert result["target_resource_id"] == sg_id
    assert result["direct_enis_attached"] == 0
    assert result["has_live_bindings"] is False
    assert result["severity"] == "SAFE"


@mock_aws
def test_topology_inspector_live_container_binding():
    ec2 = boto3.client("ec2", region_name="us-east-1")
    vpc = ec2.create_vpc(CidrBlock="10.0.0.0/16")
    subnet = ec2.create_subnet(VpcId=vpc["Vpc"]["VpcId"], CidrBlock="10.0.1.0/24")
    
    sg = ec2.create_security_group(
        GroupName="ecs-order-sg",
        Description="ECS Order Processing SG",
        VpcId=vpc["Vpc"]["VpcId"],
    )
    sg_id = sg["GroupId"]

    # Provision simulated ENI for active ECS Fargate task
    task_arn = "arn:aws:ecs:us-east-1:123456789012:task/order-cluster/a1b2c3d4e5f67890"
    eni = ec2.create_network_interface(
        SubnetId=subnet["Subnet"]["SubnetId"],
        Groups=[sg_id],
        Description=f"arn:aws:ecs:us-east-1:123456789012:task/order-cluster/a1b2c3d4e5f67890 attachment",
    )
    eni_id = eni["NetworkInterface"]["NetworkInterfaceId"]

    result = inspect_security_group_blast_radius(security_group_id=sg_id, region_name="us-east-1")

    assert result["target_resource_id"] == sg_id
    assert result["direct_enis_attached"] == 1
    assert result["has_live_bindings"] is True
    assert result["severity"] == "CRITICAL"
    assert len(result["severed_containers"]) == 1
    assert result["severed_containers"][0] == task_arn
    assert result["workloads"][0]["eni_id"] == eni_id
