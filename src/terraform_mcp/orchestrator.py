"""
MCP Mesh Orchestrator Client.
Coordinates concurrent discovery queries across AWS-Live-Topology-Inspector and
AWS-FinOps-Cost-Inspector MCP servers, aggregating results and generating deterministic PR verdicts.
"""

import asyncio
import time
from typing import Any, Dict, List, Optional, Union
from terraform_mcp.models import (
    GateVerdict,
    PlanEvaluationReport,
    ParsedPlanChanges,
    SecurityGroupBlastRadiusResult,
    FinOpsCostEfficiencyResult,
)
from terraform_mcp.plan_parser import parse_terraform_plan
from terraform_mcp.topology_server import inspect_security_group_blast_radius
from terraform_mcp.finops_server import inspect_resource_cost_efficiency


class MeshOrchestrator:
    """
    Coordinates asynchronous execution of MCP tools across Topology & FinOps discovery servers.
    """

    def __init__(self, region_name: str = "us-east-1", endpoint_url: Optional[str] = None):
        self.region_name = region_name
        self.endpoint_url = endpoint_url

    async def evaluate_plan(
        self, plan_data: Union[str, Dict[str, Any], ParsedPlanChanges]
    ) -> PlanEvaluationReport:
        """
        Parses and evaluates an AST execution plan across the MCP mesh in parallel.
        """
        start_time = time.perf_counter()

        if isinstance(plan_data, ParsedPlanChanges):
            parsed = plan_data
        else:
            parsed = parse_terraform_plan(plan_data)

        tasks = []

        # 1. Dispatch Security Group topology discovery tasks
        for sg_change in parsed.security_group_changes:
            tasks.append(self._discover_sg_topology(sg_change.resource_id))

        # 2. Dispatch FinOps compute resize discovery tasks
        for resize in parsed.compute_resizes:
            tasks.append(
                self._discover_compute_finops(
                    resource_id=resize.resource_id,
                    resource_type=resize.resource_type,
                    current_type=resize.current_type,
                    proposed_new_type=resize.proposed_type,
                )
            )

        # 3. Dispatch Route / Egress discovery tasks
        for route in parsed.route_changes:
            if not route.has_vpc_endpoint:
                tasks.append(
                    self._discover_compute_finops(
                        resource_id=route.resource_id,
                        resource_type="route_table",
                    )
                )

        # Concurrently execute all MCP discovery queries
        results = await asyncio.gather(*tasks, return_exceptions=True) if tasks else []

        topology_results: List[SecurityGroupBlastRadiusResult] = []
        finops_results: List[FinOpsCostEfficiencyResult] = []

        for res in results:
            if isinstance(res, Exception):
                continue
            if isinstance(res, SecurityGroupBlastRadiusResult):
                topology_results.append(res)
            elif isinstance(res, FinOpsCostEfficiencyResult):
                finops_results.append(res)

        # Determine overall verdict
        overall_verdict = GateVerdict.APPROVED

        # Check for Critical Reliability Blast-Radius
        for topo in topology_results:
            if topo.severity == "CRITICAL" or len(topo.severed_containers) > 0 or len(topo.target_group_arns) > 0:
                overall_verdict = GateVerdict.BLOCK_PR_CRITICAL_BLAST_RADIUS
                break

        # Check for Structural FinOps Waste if not already blocked on reliability
        if overall_verdict != GateVerdict.BLOCK_PR_CRITICAL_BLAST_RADIUS:
            for fin in finops_results:
                if fin.is_overprovisioned or fin.finops_verdict == "BLOCK_PR_FINOPS_WASTE":
                    overall_verdict = GateVerdict.BLOCK_PR_FINOPS_WASTE
                    break
                elif fin.finops_verdict == "WARNING_FINOPS_EGRESS":
                    overall_verdict = GateVerdict.WARNING_FINOPS_EGRESS

        duration_ms = (time.perf_counter() - start_time) * 1000.0

        markdown_summary = self._build_markdown_report(
            verdict=overall_verdict,
            duration_ms=duration_ms,
            mutation_summary=parsed.mutation_summary,
            topology_results=topology_results,
            finops_results=finops_results,
        )

        return PlanEvaluationReport(
            overall_verdict=overall_verdict,
            evaluation_duration_ms=round(duration_ms, 2),
            mutation_summary=parsed.mutation_summary,
            topology_results=topology_results,
            finops_results=finops_results,
            summary_markdown=markdown_summary,
        )

    async def _discover_sg_topology(self, security_group_id: str) -> SecurityGroupBlastRadiusResult:
        raw = inspect_security_group_blast_radius(
            security_group_id,
            self.region_name,
            self.endpoint_url,
        )
        return SecurityGroupBlastRadiusResult(**raw)

    async def _discover_compute_finops(
        self,
        resource_id: str,
        resource_type: str = "ec2_or_ecs",
        current_type: Optional[str] = None,
        proposed_new_type: Optional[str] = None,
    ) -> FinOpsCostEfficiencyResult:
        raw = inspect_resource_cost_efficiency(
            resource_id,
            resource_type,
            current_type,
            proposed_new_type,
            14,
            self.region_name,
            self.endpoint_url,
        )
        return FinOpsCostEfficiencyResult(**raw)

    def _build_markdown_report(
        self,
        verdict: GateVerdict,
        duration_ms: float,
        mutation_summary: Optional[Any],
        topology_results: List[SecurityGroupBlastRadiusResult],
        finops_results: List[FinOpsCostEfficiencyResult],
    ) -> str:
        verdict_badge = {
            GateVerdict.APPROVED: "### :white_check_mark: IaC Pre-Merge Gate: APPROVED",
            GateVerdict.WARNING_FINOPS_EGRESS: "### :warning: IaC Pre-Merge Gate: WARNING (FinOps Data Egress)",
            GateVerdict.BLOCK_PR_FINOPS_WASTE: "### :no_entry_sign: IaC Pre-Merge Gate: BLOCKED (Structural Cloud Waste)",
            GateVerdict.BLOCK_PR_CRITICAL_BLAST_RADIUS: "### :fire: IaC Pre-Merge Gate: BLOCKED (Critical Blast Radius)",
        }.get(verdict, "### IaC Pre-Merge Gate Verdict")

        lines = [
            verdict_badge,
            f"**Evaluation Latency:** `{duration_ms:.2f} ms` | **Protocol:** MCP JSON-RPC Mesh",
            "",
            "#### 1. Speculative State Mutation Ledger (Terraform Plan Diff)",
        ]

        if mutation_summary and mutation_summary.items:
            lines.append(f"**Plan Summary:** `+{mutation_summary.to_add} to add`, `~{mutation_summary.to_change} to change`, `-{mutation_summary.to_destroy} to destroy`, `⚠️{mutation_summary.to_replace} to replace`")
            lines.append("")
            lines.append("| Action | Resource Address | Type | Details |")
            lines.append("| :--- | :--- | :--- | :--- |")
            for item in mutation_summary.items[:15]:
                lines.append(f"| {item.action_icon} **{item.action}** | `{item.address}` | `{item.resource_type}` | {item.details or '-'} |")
            if len(mutation_summary.items) > 15:
                lines.append(f"| ... | *and {len(mutation_summary.items) - 15} more resources* | | |")
        else:
            lines.append("- *No resource mutations detected in speculative plan.*")

        lines.extend([
            "",
            "#### 2. Reliability & Dynamic Topology Blast Radius",
        ])

        if not topology_results:
            lines.append("- *No security group mutations detected.*")
        else:
            for topo in topology_results:
                status_icon = ":fire:" if topo.severity == "CRITICAL" else (":warning:" if topo.severity == "WARNING" else ":white_check_mark:")
                lines.append(f"- {status_icon} **Resource:** `{topo.target_resource_id}` — **Severity:** `{topo.severity}`")
                lines.append(f"  - **Direct ENIs Attached:** {topo.direct_enis_attached}")
                if topo.severed_containers:
                    lines.append(f"  - **Severed Live Workloads:** {len(topo.severed_containers)} task bindings")
                    for c in topo.severed_containers[:5]:
                        lines.append(f"    - `{c}`")
                if topo.target_group_arns:
                    lines.append(f"  - **Active ALB/NLB Target Groups:** {len(topo.target_group_arns)}")

        lines.extend([
            "",
            "#### 3. FinOps Utilization & Egress Audit",
        ])

        if not finops_results:
            lines.append("- *No compute or network scaling deltas detected.*")
        else:
            for fin in finops_results:
                icon = ":no_entry_sign:" if fin.is_overprovisioned else ":white_check_mark:"
                lines.append(f"- {icon} **Resource:** `{fin.resource_id}` ({fin.current_instance_type or 'current'} -> {fin.proposed_new_type or 'new'})")
                lines.append(f"  - **Observed P99 CPU:** `{fin.observed_peak_cpu_percent}%`")
                if fin.projected_monthly_compute_waste_usd > 0:
                    lines.append(f"  - **Projected Compute Waste:** `+${fin.projected_monthly_compute_waste_usd:.2f}/mo`")
                if fin.projected_monthly_network_waste_usd > 0:
                    lines.append(f"  - **Projected Cross-AZ Egress Leak:** `+${fin.projected_monthly_network_waste_usd:.2f}/mo`")
                for rec in fin.recommendations:
                    lines.append(f"  - :bulb: *{rec}*")

        lines.append("")
        lines.append("---")
        lines.append("*Generated by [terraform-mcp](https://github.com/imashish-in/terraform-mcp)*")
        return "\n".join(lines)
