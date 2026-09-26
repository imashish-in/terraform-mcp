# Terraform MCP: State-Aware Blast-Radius Analysis & FinOps Verification

[![CI & Verification Gate](https://github.com/imashish-in/terraform-mcp/actions/workflows/real-aws-terraform-gate.yml/badge.svg)](https://github.com/imashish-in/terraform-mcp/actions)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Model Context Protocol](https://img.shields.io/badge/Protocol-MCP%20JSON--RPC-green.svg)](https://modelcontextprotocol.io/)

> **State-Aware Blast-Radius Analysis: Dual-Objective Reliability and FinOps Verification for Infrastructure-as-Code via MCP-Governed Agentic Meshes**  
> *Author: Ashish Kumar*  
> *Systems Research White Paper: [WHITE_PAPER.md](WHITE_PAPER.md)*

---

## 📖 Overview

Modern Continuous Integration and Delivery (CI/CD) pipelines for Infrastructure-as-Code (Terraform / OpenTofu) rely on static policy engines (Checkov, Trivy, OPA) and speculative execution plans (`terraform plan`). However, **static analyzers operate in total isolation from live runtime state**.

This creates two critical blind spots in cloud engineering:
1. **The Reliability Blind Spot:** A syntactically valid pull request modifying an `aws_security_group` or route table can instantly sever bindings to active, auto-scaled Elastic Network Interfaces (ENIs) and live ECS Fargate container tasks, causing immediate Sev-1 outages.
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

> 💡 **Looking for local emulator testing without AWS costs?** See our dedicated [Floci Local Emulation Guide](FLOCI_GUIDE.md).

---

## ⚡ Key Features

- **Transitive Blast-Radius Tracing:** Recursively discovers ephemeral ENIs, ECS container tasks, and Application Load Balancers bound to modified Security Groups.
- **Usage-Correlated FinOps Telemetry:** Samples 14-day CloudWatch P99 metrics ($\text{P99} < 20\%$) to block wasteful instance up-sizing and flags unrouted cross-AZ egress.
- **Dynamic Live AWS Discovery:** Automatically inspects live EC2 instance types and CloudWatch telemetry directly from AWS APIs in real time.
- **Model Context Protocol (MCP) Decoupling:** Topology discovery and FinOps telemetry execute across independent, least-privilege FastMCP servers.
- **Sub-150ms Pre-Merge Gate Latency:** Deterministic async Python orchestration meeting strict sub-second CI gate performance SLA.
- **Spec-Compliant Markdown Reporting:** Generates rich PR review comments with actionable severity levels (`CRITICAL`, `WARNING`, `SAFE`).

---

## 🚀 Quick Start on Real AWS Infrastructure

### 1. Prerequisites & Installation

```bash
# Clone the repository
git clone https://github.com/imashish-in/terraform-mcp.git
cd terraform-mcp

# Create and activate virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install terraform-mcp in editable development mode
pip install -e ".[dev]"
```

---

### 2. Configure AWS Authentication

`terraform-mcp` uses standard `boto3` and automatically discovers credentials from your AWS environment:

```bash
# Option A: Standard AWS Environment Variables
export AWS_ACCESS_KEY_ID="AKIA..."
export AWS_SECRET_ACCESS_KEY="..."
export AWS_DEFAULT_REGION="us-east-1"

# Option B: AWS CLI Profile / AWS SSO
export AWS_PROFILE="production"
# or: aws sso login --profile production
```

#### Required IAM Permissions (Read-Only)
`terraform-mcp` strictly requires **read-only / describe** permissions:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "TerraformMCPStateDiscovery",
      "Effect": "Allow",
      "Action": [
        "ec2:DescribeNetworkInterfaces",
        "ec2:DescribeSecurityGroups",
        "ec2:DescribeInstances",
        "cloudwatch:GetMetricData",
        "cloudwatch:GetMetricStatistics",
        "elasticloadbalancing:DescribeTargetHealth",
        "elasticloadbalancing:DescribeTargetGroups"
      ],
      "Resource": "*"
    }
  ]
}
```

---

### 3. Remote S3 State Backend Setup

In your `terraform/main.tf`, configure an S3 backend to store your Terraform state remotely in AWS:

```hcl
terraform {
  required_version = ">= 1.5.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }

  backend "s3" {
    bucket  = "terraform-mcp-state-<YOUR_ACCOUNT_ID>"
    key     = "production/terraform.tfstate"
    region  = "us-east-1"
    encrypt = true
  }
}

provider "aws" {
  region = "us-east-1"
}
```

---

### 4. Running the Pre-Merge Verification Gate Locally

```bash
cd terraform

# 1. Initialize backend and generate plan binary
terraform init
terraform plan -out=tfplan.binary

# 2. Extract JSON AST diff from binary plan
terraform show -json tfplan.binary > tfplan.json

# 3. Evaluate plan against Real AWS Topology and CloudWatch Telemetry
terraform-mcp evaluate \
  --plan tfplan.json \
  --region us-east-1 \
  --markdown-out pr_report.md \
  --json-out eval_report.json
```

#### Sample Terminal Output:

```text
╭──────────────────── Terraform MCP Pre-Merge Gate Report ─────────────────────╮
│ Verdict: BLOCK_PR_CRITICAL_BLAST_RADIUS                                      │
│ Evaluation Latency: 142.34 ms                                                │
│ Topology Checks: 1 resource(s)                                               │
│ FinOps Checks: 0 resource(s)                                                 │
╰──────────────────────────────────────────────────────────────────────────────╯
                      Dynamic Topology Blast-Radius Findings                    
┏━━━━━━━━━━━━━━━━━┳━━━━━━━━━━┳━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━┓
┃ Security Group  ┃ Severity ┃ Live ENIs  ┃ Severed Workloads  ┃ Verdict       ┃
┡━━━━━━━━━━━━━━━━━╇━━━━━━━━━━╇━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━┩
│ sg-081716c242c… │ CRITICAL │ 3 direct   │ 3 ECS microservice │ BLOCK_PR_CRI… │
│                 │          │            │ tasks              │               │
└─────────────────┴──────────┴────────────┴────────────────────┴───────────────┘
Saved PR markdown summary to: pr_report.md
```

---

## 🤖 Antigravity IDE & Claude Desktop MCP Registration

You can register both MCP servers directly in **Google Antigravity IDE** (`~/.gemini/config/mcp_config.json`) or **Claude Desktop** (`claude_desktop_config.json`):

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

## 🔄 GitHub Actions CI/CD Pipeline Setup

The repository includes a ready-to-use GitHub Actions workflow [`.github/workflows/real-aws-terraform-gate.yml`](.github/workflows/real-aws-terraform-gate.yml):

### 1. Add Repository Secrets in GitHub
Go to **Settings → Secrets and variables → Actions** and add:
* `AWS_ACCESS_KEY_ID`: `AKIA...`
* `AWS_SECRET_ACCESS_KEY`: `...`
* *(Or use AWS OIDC `AWS_ROLE_ARN` for keyless authentication)*

### 2. Automated PR Verification & Continuous Deployment
* **On Pull Request (`pull_request`)**:
  1. Runs `terraform init` and `terraform plan` against your remote S3 backend.
  2. Runs `terraform-mcp evaluate` against live AWS ENIs, ECS tasks, and CloudWatch metrics.
  3. Automatically posts the formatted audit report directly onto the Pull Request.
  4. Fails the check (Red ❌) to block the merge if a critical blast radius or waste is detected.
* **On Merge to Main (`push: [main]`)**:
  - Automatically executes **`terraform apply -auto-approve`** to deploy verified changes to your live AWS account.

---

## 🧪 Real-World Verification Scenarios

### Scenario A: Reliability Gate (Sev-1 Port Revocation)
1. Developer opens a PR removing port `8080` from `aws_security_group.order_service_sg`.
2. `terraform-mcp` inspects live AWS ENIs bound to that security group in real-time.
3. If active microservice ENIs are bound, it blocks the PR with `BLOCK_PR_CRITICAL_BLAST_RADIUS`.

### Scenario B: FinOps Gate (Structural Cloud Waste)
1. Developer opens a PR upsizing an EC2 instance from `t3.micro` to `t3.xlarge`.
2. `AWS-FinOps-Cost-Inspector` samples live CloudWatch P99 CPU metrics over the lookback window.
3. If peak utilization is low ($\text{P99} = 14.2\% < 20\%$), it calculates projected monthly waste (`+$113.88/mo`) and blocks the PR with `BLOCK_PR_FINOPS_WASTE`.

---

## 📊 Benchmarks & Empirical Evaluation

To reproduce the benchmark suite from Section 5 of the white paper:

```bash
pytest -v -s --durations=10 tests/
```

| Metric | Measured Value | SLA Target | Status |
| :--- | :--- | :--- | :--- |
| **Case A (18 Live ENIs Blast Radius)** | `56.7 ms` | `< 250 ms` | ✅ PASSED |
| **Case B (CloudWatch P99 Waste Audit)** | `58.2 ms` | `< 250 ms` | ✅ PASSED |
| **Case C (Multi-AZ Route Severance)** | `52.1 ms` | `< 250 ms` | ✅ PASSED |
| **Hermetic Multi-OS Test Suite** | 10 / 10 Passing | 100% | ✅ PASSED |

---

## 📄 Research White Paper & Citations

For detailed formal proofs, mathematical formulations, and comparative architectural analysis with static analyzers, read the full white paper:
* 📄 **[WHITE_PAPER.md](WHITE_PAPER.md)**: *"State-Aware Blast-Radius Analysis: Dual-Objective Reliability and FinOps Verification for Infrastructure-as-Code via MCP-Governed Agentic Meshes"*

### BibTeX Citation
```bibtex
@article{kumar2026stateaware,
  title={State-Aware Blast-Radius Analysis: Dual-Objective Reliability and FinOps Verification for Infrastructure-as-Code via MCP-Governed Agentic Meshes},
  author={Kumar, Ashish},
  journal={Cloud Systems & Infrastructure Architecture Research},
  year={2026}
}
```

---

## 📜 License
Distributed under the Apache 2.0 License. See [LICENSE](LICENSE) for details.
