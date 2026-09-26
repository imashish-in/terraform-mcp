"""
Command-line interface (CLI) for terraform-mcp.
Enables pre-merge CI/CD pipeline gate evaluation, running MCP servers, and benchmark execution.
"""

import asyncio
import json
import sys
from pathlib import Path
import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from terraform_mcp.orchestrator import MeshOrchestrator
from terraform_mcp.models import GateVerdict

console = Console()


@click.group()
@click.version_option()
def main():
    """Terraform MCP: State-Aware Blast Radius & FinOps Verification Gate."""
    pass


@main.command(name="evaluate")
@click.option(
    "--plan",
    "-p",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="Path to Terraform plan JSON file (from `terraform show -json tfplan.binary`)",
)
@click.option("--region", "-r", default="us-east-1", help="AWS Region (default: us-east-1)")
@click.option("--endpoint-url", envvar="AWS_ENDPOINT_URL", help="Custom AWS endpoint URL (Floci / LocalStack)")
@click.option("--markdown-out", type=click.Path(dir_okay=False, path_type=Path), help="File to write PR markdown comment")
@click.option("--json-out", type=click.Path(dir_okay=False, path_type=Path), help="File to write JSON evaluation report")
@click.option("--fail-on-block/--no-fail", default=True, help="Exit with non-zero status code if PR is blocked")
def evaluate_cmd(plan, region, endpoint_url, markdown_out, json_out, fail_on_block):
    """Evaluate a Terraform Plan AST against live cloud topology and FinOps metrics."""
    if not plan:
        if not sys.stdin.isatty():
            plan_content = sys.stdin.read()
        else:
            console.print("[red]Error:[/red] Please provide a plan file using `--plan` or pipe JSON via stdin.")
            sys.exit(2)
    else:
        plan_content = plan.read_text(encoding="utf-8")

    orchestrator = MeshOrchestrator(region_name=region, endpoint_url=endpoint_url)

    with console.status("[bold green]Running State-Aware MCP Mesh Evaluation..."):
        report = asyncio.run(orchestrator.evaluate_plan(plan_content))

    # Display Report in Terminal
    console.print()
    verdict_style = {
        GateVerdict.APPROVED: "bold green",
        GateVerdict.WARNING_FINOPS_EGRESS: "bold yellow",
        GateVerdict.BLOCK_PR_FINOPS_WASTE: "bold red",
        GateVerdict.BLOCK_PR_CRITICAL_BLAST_RADIUS: "bold red",
    }.get(report.overall_verdict, "bold white")

    panel = Panel(
        f"[bold]Verdict:[/bold] [{verdict_style}]{report.overall_verdict.value}[/{verdict_style}]\n"
        f"[bold]Evaluation Latency:[/bold] {report.evaluation_duration_ms:.2f} ms\n"
        f"[bold]Topology Checks:[/bold] {len(report.topology_results)} resource(s)\n"
        f"[bold]FinOps Checks:[/bold] {len(report.finops_results)} resource(s)",
        title="[bold cyan]Terraform MCP Pre-Merge Gate Report[/bold cyan]",
        border_style="cyan",
    )
    console.print(panel)

    # Topology Findings Table
    if report.topology_results:
        table = Table(title="Topology Blast Radius Findings", show_header=True, header_style="bold magenta")
        table.add_column("Security Group", style="cyan")
        table.add_column("Severity", style="bold")
        table.add_column("Live ENIs", justify="right")
        table.add_column("Severed Containers", justify="right")
        table.add_column("Message")

        for topo in report.topology_results:
            sev_color = "red" if topo.severity == "CRITICAL" else ("yellow" if topo.severity == "WARNING" else "green")
            table.add_row(
                topo.target_resource_id,
                f"[{sev_color}]{topo.severity}[/{sev_color}]",
                str(topo.direct_enis_attached),
                str(len(topo.severed_containers)),
                topo.message,
            )
        console.print(table)

    # FinOps Findings Table
    if report.finops_results:
        table = Table(title="FinOps Utilization & Waste Findings", show_header=True, header_style="bold green")
        table.add_column("Resource ID", style="cyan")
        table.add_column("P99 CPU", justify="right")
        table.add_column("Compute Delta", justify="right")
        table.add_column("Monthly Waste", justify="right", style="red")
        table.add_column("Verdict", style="bold")

        for fin in report.finops_results:
            verdict_color = "red" if fin.is_overprovisioned else "green"
            table.add_row(
                fin.resource_id,
                f"{fin.observed_peak_cpu_percent}%",
                f"{fin.current_instance_type or 'N/A'} -> {fin.proposed_new_type or 'N/A'}",
                f"+${fin.projected_monthly_compute_waste_usd:.2f}/mo" if fin.projected_monthly_compute_waste_usd > 0 else "$0.00",
                f"[{verdict_color}]{fin.finops_verdict}[/{verdict_color}]",
            )
        console.print(table)

    # Output Files
    if markdown_out:
        markdown_out.write_text(report.summary_markdown, encoding="utf-8")
        console.print(f"[dim]Saved PR markdown summary to: {markdown_out}[/dim]")

    if json_out:
        json_out.write_text(json.dumps(report.model_dump(), indent=2), encoding="utf-8")
        console.print(f"[dim]Saved JSON report to: {json_out}[/dim]")

    # Exit Status
    if fail_on_block and report.overall_verdict in (
        GateVerdict.BLOCK_PR_CRITICAL_BLAST_RADIUS,
        GateVerdict.BLOCK_PR_FINOPS_WASTE,
    ):
        console.print("\n[bold red]CI Gate Failed: Pull Request blocked due to state-aware blast radius / waste policy violation.[/bold red]")
        sys.exit(1)
    else:
        console.print("\n[bold green]CI Gate Passed: Configuration cleared for deployment.[/bold green]")
        sys.exit(0)


@main.command(name="serve-topology")
def serve_topology_cmd():
    """Start the AWS-Live-Topology-Inspector FastMCP server (stdio)."""
    from terraform_mcp.topology_server import run_server
    run_server()


@main.command(name="serve-finops")
def serve_finops_cmd():
    """Start the AWS-FinOps-Cost-Inspector FastMCP server (stdio)."""
    from terraform_mcp.finops_server import run_server
    run_server()


if __name__ == "__main__":
    main()
