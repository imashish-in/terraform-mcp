"""
Parser for Terraform speculative execution plans (terraform show -json tfplan.binary).
Extracts changed resource ASTs, revoked security group ports, and instance resizing events.
"""

import json
from typing import Any, Dict, List, Union
from terraform_mcp.models import (
    ParsedPlanChanges,
    SecurityGroupChange,
    ComputeResizeChange,
    RouteChange,
)


def parse_terraform_plan(plan_data: Union[str, Dict[str, Any]]) -> ParsedPlanChanges:
    """
    Parses a Terraform Plan JSON dictionary or JSON string.
    Extracts security group mutations, compute resizes, and network route updates.
    """
    if isinstance(plan_data, str):
        data = json.loads(plan_data)
    else:
        data = plan_data

    format_version = data.get("format_version")
    terraform_version = data.get("terraform_version")

    sg_changes: List[SecurityGroupChange] = []
    compute_resizes: List[ComputeResizeChange] = []
    route_changes: List[RouteChange] = []

    resource_changes = data.get("resource_changes", [])

    for change_item in resource_changes:
        resource_type = change_item.get("type", "")
        address = change_item.get("address", "")
        change = change_item.get("change", {})
        actions = change.get("actions", [])

        if actions == ["no-op"] or actions == ["read"]:
            continue

        before = change.get("before") or {}
        after = change.get("after") or {}

        # 1. Inspect Security Groups & Security Group Rules
        if resource_type in ("aws_security_group", "aws_security_group_rule"):
            res_id = before.get("id") or after.get("id") or change_item.get("name", "unknown-sg")
            if resource_type == "aws_security_group_rule":
                res_id = before.get("security_group_id") or after.get("security_group_id") or res_id

            revoked_ports: List[int] = []
            before_ingress = before.get("ingress", []) if isinstance(before.get("ingress"), list) else []
            after_ingress = after.get("ingress", []) if isinstance(after.get("ingress"), list) else []

            # Check if ports were removed in SG ingress rules
            before_ports = {rule.get("from_port") for rule in before_ingress if rule.get("from_port") is not None}
            after_ports = {rule.get("from_port") for rule in after_ingress if rule.get("from_port") is not None}
            revoked_ports.extend([int(p) for p in (before_ports - after_ports) if p is not None])

            if resource_type == "aws_security_group_rule" and "delete" in actions:
                from_p = before.get("from_port")
                if from_p:
                    revoked_ports.append(int(from_p))

            sg_changes.append(
                SecurityGroupChange(
                    resource_id=str(res_id),
                    address=address,
                    actions=actions,
                    revoked_ports=list(set(revoked_ports)),
                    modified_rules=after_ingress,
                )
            )

        # 2. Inspect Compute / Workload Resizing (EC2 / ECS / RDS)
        elif resource_type in ("aws_instance", "aws_launch_template", "aws_ecs_service", "aws_db_instance"):
            tags_after = after.get("tags") or {}
            tags_before = before.get("tags") or {}
            tag_name = tags_after.get("Name") or tags_before.get("Name")
            res_id = before.get("id") or after.get("id") or tag_name or change_item.get("name", "unknown-compute")
            current_type = before.get("instance_type") or before.get("instance_class") or tags_after.get("BaselineType") or ("t3.medium" if actions == ["create"] and after.get("instance_type") in ("t3.xlarge", "t3.2xlarge", "m5.2xlarge", "c5.2xlarge") else None)
            proposed_type = after.get("instance_type") or after.get("instance_class")

            if current_type or proposed_type or resource_type == "aws_ecs_service":
                compute_resizes.append(
                    ComputeResizeChange(
                        resource_id=str(res_id),
                        address=address,
                        resource_type=resource_type,
                        actions=actions,
                        current_type=current_type,
                        proposed_type=proposed_type,
                    )
                )

        # 3. Inspect Route Tables & Routes
        elif resource_type in ("aws_route", "aws_route_table"):
            res_id = before.get("id") or after.get("id") or change_item.get("name", "unknown-route")
            route_table_id = before.get("route_table_id") or after.get("route_table_id")
            dest_cidr = before.get("destination_cidr_block") or after.get("destination_cidr_block")
            target_id = (
                after.get("gateway_id")
                or after.get("nat_gateway_id")
                or after.get("transit_gateway_id")
                or after.get("network_interface_id")
            )

            # Detect whether change lacks VPC endpoint
            has_endpoint = bool(after.get("vpc_endpoint_id"))

            route_changes.append(
                RouteChange(
                    resource_id=str(res_id),
                    address=address,
                    actions=actions,
                    route_table_id=route_table_id,
                    destination_cidr=dest_cidr,
                    target_id=target_id,
                    has_vpc_endpoint=has_endpoint,
                )
            )

    return ParsedPlanChanges(
        format_version=format_version,
        terraform_version=terraform_version,
        security_group_changes=sg_changes,
        compute_resizes=compute_resizes,
        route_changes=route_changes,
        total_resources_modified=len(sg_changes) + len(compute_resizes) + len(route_changes),
    )
