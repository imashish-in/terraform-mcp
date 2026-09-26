# Terraform MCP: State-Aware Blast-Radius Analysis & FinOps Verification

[![CI & Verification Gate](https://github.com/ashishkumar/terraform-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/ashishkumar/terraform-mcp/actions)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Model Context Protocol](https://img.shields.io/badge/Protocol-MCP%20JSON--RPC-green.svg)](https://modelcontextprotocol.io/)

> **State-Aware Blast-Radius Analysis: Dual-Objective Reliability and FinOps Verification for Infrastructure-as-Code via MCP-Governed Agentic Meshes**  
> *Author: Ashish Kumar*  
> *Systems Research White Paper & Open-Source Implementation*

---

## Overview

Modern Continuous Integration and Delivery (CI/CD) pipelines for Infrastructure-as-Code (Terraform / OpenTofu) rely on static policy engines (Checkov, Trivy, OPA) and speculative execution plans (`terraform plan`). However, **static analyzers operate in total isolation from live runtime state**.

This creates two critical blind spots:
1. **The Reliability Blind Spot:** A syntactically valid pull request modifying an `aws_security_group` or route table can instantly sever bindings to active, auto-scaled Elastic Network Interfaces (ENIs) and live ECS Fargate container tasks, causing immediate outages.
2. **The FinOps Blind Spot:** Static cost estimators (e.g. Infracost) calculate flat rate deltas but are blind to live P99 CPU/memory utilization and cross-AZ data egress leaks ($0.01/GB).

`terraform-mcp` bridges declarative IaC intent with live operational realities using the **Model Context Protocol (MCP)** across a decoupled, least-privilege discovery mesh:

```
┌────────────────────────────────────────────────────────────────────────┐
│ CI/CD Pipeline Runner (GitHub Actions / GitLab CI)                     │
│                                                                        │
│  1. terraform show -json tfplan.binary ──> AST Extraction              │
│  2. Ephemeral OIDC Token Exchange ───────> Read-Only AWS STS Token     │
│                                                                        │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │                   MCP ORCHESTRATION MESH                         │  │
│  │   - Concurrent FastMCP Queries (asyncio.gather)                  │  │
│  │   - Deterministic Gating Rules (Zero Token Hallucinations)       │  │
│  └───────────────┬──────────────────────────────────┬───────────────┘  │
└──────────────────┼──────────────────────────────────┼──────────────────┘
                   │ JSON-RPC                         │ JSON-RPC
                   │ tools/call                       │ tools/call
                   ▼                                  ▼
┌──────────────────────────────────────┐  ┌──────────────────────────────┐
│ AWS Live-Topology MCP Server         │  │ FinOps Telemetry MCP Server  │
│                                      │  │                              │
│ - Tool: inspect_security_group       │  │ - Tool: inspect_cost_waste   │
│ - Boto3 EC2/VPC Discovery Engine     │  │ - CloudWatch P99 & Egress    │
│ - IAM: ec2:Describe*                 │  │ - IAM: cloudwatch:GetMetric* │
└──────────────────┬───────────────────┘  └──────────────┬───────────────┘
                   │                                     │
                   ▼                                     ▼
┌────────────────────────────────────────────────────────────────────────┐
│ Live AWS Cloud Infrastructure / Local Emulation Harness (Floci / Moto) │
└────────────────────────────────────────────────────────────────────────┘
```

---

## Key Features

- **Transitive Blast-Radius Tracing:** Recursively discovers ephemeral ENIs, ECS container tasks, and Application Load Balancers bound to modified Security Groups.
- **Usage-Correlated FinOps Telemetry:** Samples 14-day CloudWatch P99 metrics ($\text{P99} < 20\%$) to block wasteful instance up-sizing and flags unrouted cross-AZ egress.
- **MCP Protocol Decoupling:** Topology discovery and FinOps telemetry execute across independent, least-privilege FastMCP servers.
- **Zero-Trust Ephemeral IAM:** Requires no standing credentials; authenticates via GitHub Actions / GitLab OIDC STS tokens.
- **Sub-Second Latency:** Ingests plans and evaluates dynamic cloud graphs in $<50\text{ ms}$ (local testbed).

---

## Installation

```bash
# Clone the repository
git clone https://github.com/ashishkumar/terraform-mcp.git
cd terraform-mcp

# Install via pip
pip install -e .

# Or install with test and development dependencies
pip install -e ".[dev]"
```

---

## Quickstart & CLI Usage

### 1. Pre-Merge PR Evaluation Gate

Evaluate a Terraform speculative execution plan directly against live cloud state:

```bash
# Generate speculative plan JSON
terraform plan -out=tfplan.binary
terraform show -json tfplan.binary > tfplan.json

# Run state-aware MCP gate evaluation
terraform-mcp evaluate \
  --plan tfplan.json \
  --region us-east-1 \
  --markdown-out pr_comment.md \
  --json-out eval_report.json
```

### 2. Running MCP Discovery Servers Independently

You can run each MCP discovery server independently as standard MCP stdio services:

```bash
# Start Live-Topology Inspector MCP Server
terraform-mcp serve-topology

# Start FinOps Cost Inspector MCP Server
terraform-mcp serve-finops
```

### 3. Integrating with Claude Desktop / Cursor / Antigravity

Add the servers to your MCP configuration file (`mcp_config.json` or `claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "aws-live-topology-inspector": {
      "command": "terraform-mcp",
      "args": ["serve-topology"],
      "env": {
        "AWS_REGION": "us-east-1"
      }
    },
    "aws-finops-cost-inspector": {
      "command": "terraform-mcp",
      "args": ["serve-finops"],
      "env": {
        "AWS_REGION": "us-east-1"
      }
    }
  }
}
```

---

## Empirical Benchmark Suite

The codebase includes the testbed reproducing Section 5 of the white paper:

| Benchmark Phase | Mean Latency | Overhead | Detection Result |
| --- | --- | --- | --- |
| **Case A: Port 8080 Revocation** on SG with 18 live ECS tasks | `~23 ms` | Sub-millisecond Boto3 | **BLOCKED (CRITICAL)** (18 severed containers detected) |
| **Case B: Compute Upsize** (`t3.medium` $\to$ `t3.xlarge`) with idle workload | `~18 ms` | Sub-millisecond CloudWatch | **BLOCKED (FINOPS)** (Flagged 12.4% P99 CPU waste) |
| **Case C: Route Modification** inducing Cross-AZ egress | `~20 ms` | Fast AST traversal | **WARNING (FINOPS)** (Flagged unmitigated transfer) |

Run the benchmarks locally:

```bash
pytest -v -s tests/test_benchmarks.py
```

---

## GitHub Actions CI/CD Integration

Add the verification gate as a status check in your GitHub Actions workflow (`.github/workflows/ci.yml`):

```yaml
name: Terraform State-Aware Gate
on: [pull_request]

permissions:
  id-token: write
  contents: read
  pull-requests: write

jobs:
  verify:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install terraform-mcp

      - name: Configure AWS Credentials via OIDC
        uses: aws-actions/configure-aws-credentials@v4
        with:
          role-to-assume: arn:aws:iam::123456789012:role/TerraformMcpReadOnlyGate
          aws-region: us-east-1

      - name: Run MCP Gate Evaluation
        run: |
          terraform plan -out=tfplan.binary
          terraform show -json tfplan.binary > tfplan.json
          terraform-mcp evaluate --plan tfplan.json --markdown-out pr_report.md

      - name: Comment PR Report
        uses: actions/github-script@v7
        with:
          script: |
            const fs = require('fs');
            const report = fs.readFileSync('pr_report.md', 'utf8');
            github.rest.issues.createComment({
              issue_number: context.issue.number,
              owner: context.repo.owner,
              repo: context.repo.repo,
              body: report
            });
```

---

## Scoped Least-Privilege IAM Policy

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "TerraformMcpReadOnlyDiscovery",
      "Effect": "Allow",
      "Action": [
        "ec2:DescribeNetworkInterfaces",
        "ec2:DescribeSecurityGroups",
        "elasticloadbalancing:DescribeTargetGroups",
        "elasticloadbalancing:DescribeTargetHealth",
        "cloudwatch:GetMetricData"
      ],
      "Resource": "*"
    }
  ]
}
```

---

## Research White Paper

Read the complete systems research paper in [WHITE_PAPER.md](WHITE_PAPER.md).

---

## License

Apache License 2.0. See [LICENSE](LICENSE) for details.
