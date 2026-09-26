"""
Pydantic data models defining the MCP schemas, AST plan changes, and verification verdicts.
"""

from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class GateVerdict(str, Enum):
    APPROVED = "APPROVED"
    WARNING_FINOPS_EGRESS = "WARNING_FINOPS_EGRESS"
    BLOCK_PR_FINOPS_WASTE = "BLOCK_PR_FINOPS_WASTE"
    BLOCK_PR_CRITICAL_BLAST_RADIUS = "BLOCK_PR_CRITICAL_BLAST_RADIUS"


class ResourceAction(str, Enum):
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"
    NO_OP = "no-op"


class WorkloadBinding(BaseModel):
    eni_id: str = Field(..., description="The Elastic Network Interface ID")
    status: str = Field(..., description="Status of the ENI (in-use, available)")
    workload_description: str = Field(..., description="Description of the attached workload or task ARN")
    private_ip: Optional[str] = Field(None, description="Primary private IPv4 address")
    availability_zone: Optional[str] = Field(None, description="Availability Zone of the ENI")


class SecurityGroupBlastRadiusResult(BaseModel):
    target_resource_id: str = Field(..., description="Security Group ID evaluated")
    direct_enis_attached: int = Field(..., description="Number of direct ENIs attached to this SG")
    workloads: List[WorkloadBinding] = Field(default_factory=list, description="List of active attached workloads")
    target_group_arns: List[str] = Field(default_factory=list, description="Target Groups associated with the workloads")
    severed_containers: List[str] = Field(default_factory=list, description="Task ARNs or container IDs impacted")
    has_live_bindings: bool = Field(..., description="True if active live workloads are bound to this SG")
    severity: str = Field("SAFE", description="Severity assessment (SAFE, WARNING, CRITICAL)")
    message: str = Field("", description="Human-readable summary explanation")


class FinOpsCostEfficiencyResult(BaseModel):
    resource_id: str = Field(..., description="Target AWS resource identifier")
    resource_type: str = Field("ec2_or_ecs", description="Type of compute or database resource")
    current_instance_type: Optional[str] = Field(None, description="Current instance type")
    proposed_new_type: Optional[str] = Field(None, description="Proposed new instance type")
    observed_peak_cpu_percent: float = Field(..., description="P99 CPU utilization observed over lookback period")
    total_gb_transferred: float = Field(0.0, description="Observed network data transfer in GB")
    is_overprovisioned: bool = Field(..., description="True if compute scaling is structurally wasteful")
    projected_monthly_compute_waste_usd: float = Field(0.0, description="Projected monthly compute waste delta")
    projected_monthly_network_waste_usd: float = Field(0.0, description="Projected cross-AZ egress leak cost")
    recommendations: List[str] = Field(default_factory=list, description="Actionable FinOps recommendations")
    finops_verdict: str = Field("APPROVED", description="FinOps verdict (APPROVED, WARNING, BLOCK_PR_FINOPS_WASTE)")


class SecurityGroupChange(BaseModel):
    resource_id: str
    address: str
    actions: List[str]
    revoked_ports: List[int] = Field(default_factory=list)
    modified_rules: List[Dict[str, Any]] = Field(default_factory=list)


class ComputeResizeChange(BaseModel):
    resource_id: str
    address: str
    resource_type: str
    actions: List[str]
    current_type: Optional[str] = None
    proposed_type: Optional[str] = None


class RouteChange(BaseModel):
    resource_id: str
    address: str
    actions: List[str]
    route_table_id: Optional[str] = None
    destination_cidr: Optional[str] = None
    target_id: Optional[str] = None
    has_vpc_endpoint: bool = True


class ParsedPlanChanges(BaseModel):
    format_version: Optional[str] = None
    terraform_version: Optional[str] = None
    security_group_changes: List[SecurityGroupChange] = Field(default_factory=list)
    compute_resizes: List[ComputeResizeChange] = Field(default_factory=list)
    route_changes: List[RouteChange] = Field(default_factory=list)
    total_resources_modified: int = 0


class PlanEvaluationReport(BaseModel):
    overall_verdict: GateVerdict
    evaluation_duration_ms: float
    topology_results: List[SecurityGroupBlastRadiusResult] = Field(default_factory=list)
    finops_results: List[FinOpsCostEfficiencyResult] = Field(default_factory=list)
    summary_markdown: str = ""
