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
    ResourceMutationLedgerItem,
    PlanMutationSummary,
)


def parse_terraform_plan(plan_data: Union[str, Dict[str, Any]]) -> ParsedPlanChanges:
    """
    Parses a Terraform Plan JSON dictionary or JSON string.
    Extracts security group mutations, compute resizes, network route updates,
    and a complete state mutation ledger.
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
    ledger_items: List[ResourceMutationLedgerItem] = []

    to_add = 0
    to_change = 0
    to_destroy = 0
    to_replace = 0

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

        # Track in Speculative Mutation Ledger
        action_str = "UPDATE"
        icon = "🔄"
        if actions == ["create"]:
            action_str = "CREATE"
            icon = "➕"
            to_add += 1
        elif actions == ["delete"]:
            action_str = "DELETE"
            icon = "🗑️"
            to_destroy += 1
        elif "delete" in actions and "create" in actions:
            action_str = "REPLACE"
            icon = "⚠️"
            to_replace += 1
        elif actions == ["update"]:
            action_str = "UPDATE"
            icon = "🔄"
            to_change += 1

        details = ""
        if resource_type in ("aws_instance", "aws_launch_template"):
            b_type = before.get("instance_type")
            a_type = after.get("instance_type")
            details = f"type: {b_type} -> {a_type}" if (b_type and a_type and b_type != a_type) else f"type: {a_type or b_type}"
        elif resource_type == "aws_subnet":
            details = f"cidr: {after.get('cidr_block') or before.get('cidr_block')} ({after.get('availability_zone') or before.get('availability_zone')})"
        elif resource_type == "aws_vpc":
            details = f"cidr: {after.get('cidr_block') or before.get('cidr_block')}"
        elif resource_type in ("aws_security_group", "aws_security_group_rule"):
            details = f"group: {change_item.get('name') or address}"

        ledger_items.append(
            ResourceMutationLedgerItem(
                address=address,
                resource_type=resource_type,
                action=action_str,
                action_icon=icon,
                details=details,
            )
        )

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
            current_type = before.get("instance_type") or before.get("instance_class")
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

    mutation_summary = PlanMutationSummary(
        to_add=to_add,
        to_change=to_change,
        to_destroy=to_destroy,
        to_replace=to_replace,
        items=ledger_items,
    )

    return ParsedPlanChanges(
        format_version=format_version,
        terraform_version=terraform_version,
        security_group_changes=sg_changes,
        compute_resizes=compute_resizes,
        route_changes=route_changes,
        mutation_summary=mutation_summary,
        total_resources_modified=len(ledger_items),
    )
