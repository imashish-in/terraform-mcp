# Comprehensive Test Cases & Extended Capabilities Guide

> **Reference White Paper:**  
> *"State-Aware Blast-Radius Analysis: Dual-Objective Reliability and FinOps Verification for Infrastructure-as-Code via MCP-Governed Agentic Meshes"*  
> **Author:** Ashish Kumar  

---

## 📑 Table of Contents
1. [Executive Summary & Core Architecture](#1-executive-summary--core-architecture)
2. [Comprehensive Test Cases Matrix](#2-comprehensive-test-cases-matrix)
   - [Test Case 1: Active Port Revocation (Sev-1 Outage Blast Radius)](#test-case-1-active-port-revocation-sev-1-outage-blast-radius)
   - [Test Case 2: Safe Ingress Rule Refactoring (Zero Attached ENIs)](#test-case-2-safe-ingress-rule-refactoring-zero-attached-enis)
   - [Test Case 3: Over-Provisioned Compute Upsizing (FinOps Waste)](#test-case-3-over-provisioned-compute-upsizing-finops-waste)
   - [Test Case 4: Justified Workload Scaling (Heavy Production Load)](#test-case-4-justified-workload-scaling-heavy-production-load)
   - [Test Case 5: Unrouted Cross-AZ / Cross-Region Egress Leaks](#test-case-5-unrouted-cross-az--cross-region-egress-leaks)
   - [Test Case 6: Broken Load Balancer & Health Check Probes](#test-case-6-broken-load-balancer--health-check-probes)
   - [Test Case 7: Transitive Route Table Severance](#test-case-7-transitive-route-table-severance)
3. [Five Distinct Operational Modes (How to Use This System)](#3-five-distinct-operational-modes-how-to-use-this-system)
   - [Mode 1: Automated CI/CD Pre-Merge Gate (GitHub Actions / GitLab)](#mode-1-automated-cicd-pre-merge-gate-github-actions--gitlab)
   - [Mode 2: Interactive AI Pair Programming in Antigravity IDE & Claude Desktop](#mode-2-interactive-ai-pair-programming-in-antigravity-ide--claude-desktop)
   - [Mode 3: Local Pre-Commit CLI Evaluation](#mode-3-local-pre-commit-cli-evaluation)
   - [Mode 4: Offline & Zero-Cost Local Emulation with Floci](#mode-4-offline--zero-cost-local-emulation-with-floci)
   - [Mode 5: Continuous Production Drift & FinOps Mesh Auditing](#mode-5-continuous-production-drift--finops-mesh-auditing)
4. [Step-by-Step Test Execution Recipes](#4-step-by-step-test-execution-recipes)

---

## 1. Executive Summary & Core Architecture

Traditional static analysis engines (Checkov, Trivy, OPA, Infracost) evaluate Terraform plans in complete isolation from the live runtime state of your cloud environment.

`terraform-mcp` solves this by introducing a **least-privilege FastMCP mesh** that queries live runtime APIs (EC2 ENIs, ECS task bindings, CloudWatch P99 telemetry, and ELB target groups) during the pull request evaluation phase.

```
Speculative Plan (tfplan.json)
              │
              ▼
  [ AST Mutation Extractor ]
              │
      ┌───────┴────────────────────────┐
      ▼                                ▼
[ AWS-Live-Topology-Inspector ]   [ AWS-FinOps-Cost-Inspector ]
  • Live ENIs / ECS Bindings        • CloudWatch P99 CPU Metrics
  • Target Health Discovery         • Cross-AZ Egress Telemetry
      │                                │
      └───────┬────────────────────────┘
              ▼
  [ Deterministic Gate Engine ]
              │
      ┌───────┴────────────────────────┐
      ▼                                ▼
APPROVED (Green Light)         BLOCKED (Sev-1 / Waste)
```

---

## 2. Comprehensive Test Cases Matrix

| Test Case ID | Scenario Name | Terraform Mutation in Plan | Live Cloud Telemetry State | Expected Gate Verdict | Action Taken by CI/CD |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **TC-01** | **Sev-1 Outage Blast Radius** | Remove port `8080` from Security Group | 3+ active ECS microservices / ENIs bound | `BLOCK_PR_CRITICAL_BLAST_RADIUS` | Fails CI check (Exit 1), blocks PR merge, lists severed task ARNs |
| **TC-02** | **Safe Refactoring** | Remove port `8080` from Security Group | 0 active ENIs bound | `APPROVED` | Passes CI check (Exit 0), allows merge |
| **TC-03** | **Structural Compute Waste** | Upsize EC2 (`t3.micro` ➔ `t3.xlarge`) | Observed P99 CPU = `0.27%` (< 20%) | `BLOCK_PR_FINOPS_WASTE` | Fails CI check, reports `+$113.88/mo` projected waste |
| **TC-04** | **Justified Compute Scaling** | Upsize EC2 (`t3.micro` ➔ `t3.xlarge`) | Observed P99 CPU = `88.5%` (> 70%) | `APPROVED` | Passes CI check, validates legitimate scaling need |
| **TC-05** | **Cross-AZ Data Egress Leak** | Deploy subnets across AZs without VPC Endpoints | NetworkOut > 500 GB/mo ($0.01/GB) | `WARNING_FINOPS_EGRESS` | Comments on PR warning about `$0.02/GB` inter-AZ fee |
| **TC-06** | **ALB Probe Severance** | Remove port `443` HTTPS ingress | Target Group has 12 healthy targets | `BLOCK_PR_CRITICAL_BLAST_RADIUS` | Blocks PR, warns that ALB health checks will fail |
| **TC-07** | **Multi-AZ Route Severance** | Delete/modify `aws_route` to NAT/TGW | Cross-AZ route dependencies active | `BLOCK_PR_CRITICAL_BLAST_RADIUS` | Blocks PR, flags broken inter-subnet network paths |

---

### Detailed Test Case Specifications

#### Test Case 1: Active Port Revocation (Sev-1 Outage Blast Radius)
* **Goal**: Prevent breaking changes to live microservice communication.
* **Code Diff**:
  ```diff
  resource "aws_security_group" "order_service_sg" {
  -  ingress {
  -    from_port = 8080
  -    to_port   = 8080
  -    protocol  = "tcp"
  -  }
  ```
* **Engine Evaluation**: `AWS-Live-Topology-Inspector` queries `ec2:DescribeNetworkInterfaces(Filters=[{group-id: sg-...}])` and matches active ECS Task ARNs.
* **Result**:
  ```markdown
  ### 🔥 IaC Pre-Merge Gate: BLOCKED (Critical Blast Radius)
  - 🔥 Resource: `sg-081716c242ce025c6` — Severity: `CRITICAL`
    - Direct ENIs Attached: 3
    - Severed Live Workloads: 3 task bindings
      - `arn:aws:ecs:us-east-1:...:task/order-service/task-1`
      - `arn:aws:ecs:us-east-1:...:task/order-service/task-2`
      - `arn:aws:ecs:us-east-1:...:task/order-service/task-3`
  ```

---

#### Test Case 3: Over-Provisioned Compute Upsizing (FinOps Waste)
* **Goal**: Prevent expensive instance upsizing for idle workloads.
* **Code Diff**:
  ```diff
  resource "aws_instance" "order_worker" {
  -  instance_type = "t3.micro"
  +  instance_type = "t3.xlarge"
  }
  ```
* **Engine Evaluation**: `AWS-FinOps-Cost-Inspector` queries 14-day CloudWatch P99 CPU metrics for `order-worker-01`.
* **Result**:
  ```markdown
  ### 🚫 IaC Pre-Merge Gate: BLOCKED (Structural Cloud Waste)
  - 🚫 Resource: `i-02c5398040ebbf159` (t3.micro -> t3.xlarge)
    - Observed P99 CPU: `0.27%`
    - Projected Compute Waste: `+$113.88/mo`
    - 💡 Workload has observed a peak P99 CPU of only 0.3%. Reject resize or implement autoscaling.
  ```

---

#### Test Case 5: Unrouted Cross-AZ / Cross-Region Egress Leaks
* **Goal**: Detect high-volume cross-AZ traffic that incurs unnecessary AWS transfer fees.
* **Engine Evaluation**: Samples `NetworkOut` metric in CloudWatch. If volume $> 500\text{ GB/mo}$, it projects monthly fees at $\$0.01\text{ - }\$0.02/\text{GB}$.
* **Result**:
  ```markdown
  ### ⚠️ IaC Pre-Merge Gate: WARNING (Cross-AZ Egress Leak)
  - ⚠️ Resource: `order_worker`
    - Total Egress Volume: `1,250 GB/mo`
    - Projected Egress Cost: `+$25.00/mo`
    - 💡 Recommendation: Deploy VPC Endpoints (PrivateLink) to avoid cross-AZ NAT Gateway traversal.
  ```

---

## 3. Five Distinct Operational Modes (How to Use This System)

### Mode 1: Automated CI/CD Pre-Merge Gate (GitHub Actions / GitLab)
* **Purpose**: Fully autonomous pre-merge gating.
* **Workflow**: Developers open a PR ➔ GitHub Actions runs `terraform plan` ➔ `terraform-mcp evaluate` scans live AWS ➔ Comments on the PR ➔ Blocks bad merges.
* **Auto-Deploy**: When approved and merged to `main`, GitHub Actions runs `terraform apply -auto-approve` to real AWS.

---

### Mode 2: Interactive AI Pair Programming in Antigravity IDE & Claude Desktop
* **Purpose**: Real-time infrastructure auditing during code authoring.
* **How it works**: The AI assistant directly calls FastMCP tools (`inspect_security_group_blast_radius` and `inspect_resource_cost_efficiency`) via JSON-RPC.
* **Example Prompt**:
  > *"Hey Antigravity, I want to remove port 8080 from `order-service-sg`. Check my live AWS environment and tell me if anything will break."*

---

### Mode 3: Local Pre-Commit CLI Evaluation
* **Purpose**: Shift-left verification on local developer laptops before opening PRs.
* **Command**:
  ```bash
  terraform plan -out=tfplan.binary
  terraform show -json tfplan.binary > tfplan.json
  terraform-mcp evaluate --plan tfplan.json --region us-east-1
  ```

---

### Mode 4: Offline & Zero-Cost Local Emulation with Floci
* **Purpose**: Local integration testing and benchmark validation without cloud credentials or AWS costs.
* **How it works**: Uses `floci/floci:latest` running in Docker on port `4566`.
* **Guide**: See [FLOCI_GUIDE.md](FLOCI_GUIDE.md).

---

### Mode 5: Continuous Production Drift & FinOps Mesh Auditing
* **Purpose**: Scheduled nightly or hourly cron jobs that scan live production infrastructure to find orphaned security groups and idle over-provisioned instances.
* **Command**:
  ```bash
  # Cron execution to generate nightly markdown reports
  terraform-mcp evaluate --plan live_inventory.json --markdown-out nightly_audit.md
  ```

---

## 4. Step-by-Step Test Execution Recipes

### Recipe A: Run the Automated Unit & Benchmark Suite (Section 5 of Paper)
```bash
# Run all 10 hermetic tests with latency distribution benchmarks
pytest -v -s --durations=10 tests/
```

### Recipe B: Test Port Revocation on Live AWS
```bash
# 1. Checkout your feature branch
git checkout -b feat/test-port-revocation

# 2. Edit terraform/main.tf and delete port 8080
# 3. Generate plan
cd terraform
terraform plan -out=tfplan.binary
terraform show -json tfplan.binary > tfplan.json

# 4. Run State-Aware Evaluation
terraform-mcp evaluate --plan tfplan.json --region us-east-1
```

### Recipe C: Test CloudWatch FinOps Waste Gate on Live AWS
```bash
# 1. Edit terraform/main.tf and change instance_type to "t3.xlarge"
# 2. Generate plan
cd terraform
terraform plan -out=tfplan.binary
terraform show -json tfplan.binary > tfplan.json

# 3. Run FinOps Evaluation
terraform-mcp evaluate --plan tfplan.json --region us-east-1
```

---

## 📜 Summary
`terraform-mcp` transforms static infrastructure reviews into **real-time, state-aware verification gates** protecting both **production availability (Reliability)** and **cloud budget (FinOps)** across any cloud environment.
