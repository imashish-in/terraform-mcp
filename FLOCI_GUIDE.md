# Local Cloud Emulation Guide with Floci

This guide explains how to run, test, and benchmark `terraform-mcp` locally using **[Floci](https://floci.io/)** (a high-performance local AWS cloud emulator) with **zero AWS costs and zero cloud credentials**.

---

## 🐳 1. Starting Floci with Docker

Floci runs in a lightweight container and emulates AWS EC2, VPC, ECS, CloudWatch, and ELB APIs on port `4566`.

### Start Floci Container:
```bash
docker run -d \
  --name floci \
  -p 4566:4566 \
  -v /var/run/docker.sock:/var/run/docker.sock \
  floci/floci:latest
```

> [!IMPORTANT]
> - Do not bind host port `4500` manually, as Floci dynamically launches an internal `floci-ui` sidecar container that binds to port `4500`.
> - Mounting `/var/run/docker.sock` allows Floci to manage local containerized compute tasks.

### Access Floci Web UI:
Once the container is running, open your web browser:
👉 **[http://localhost:4566/_floci/ui](http://localhost:4566/_floci/ui)**

---

## 🛠️ 2. Environment Variables for Floci

Set the following environment variables in your terminal session to route all `boto3` and `terraform` calls to the local Floci container:

```bash
export AWS_ACCESS_KEY_ID="test"
export AWS_SECRET_ACCESS_KEY="test"
export AWS_DEFAULT_REGION="us-east-1"
export AWS_ENDPOINT_URL="http://localhost:4566"
```

---

## 🧪 3. Running Pre-Built Simulation Scenarios

`terraform-mcp` provides automated scripts to inject realistic operational topologies into Floci:

### Scenario 1: Simulating an Active Production Outage
```bash
# 1. Provision a VPC, Security Group, and 3 active live ECS microservice ENIs in Floci
python simulate_outage.py

# 2. Evaluate the port-revocation plan against the live Floci topology
terraform-mcp evaluate \
  --plan live_plan_case_a.json \
  --endpoint-url http://localhost:4566 \
  --markdown-out pr_report.md
```

#### Expected Output:
```text
╭──────────────────── Terraform MCP Pre-Merge Gate Report ─────────────────────╮
│ Verdict: BLOCK_PR_CRITICAL_BLAST_RADIUS                                      │
│ Evaluation Latency: 124.50 ms                                                │
│ Topology Checks: 1 resource(s)                                               │
│ FinOps Checks: 0 resource(s)                                                 │
╰──────────────────────────────────────────────────────────────────────────────╯
                      Dynamic Topology Blast-Radius Findings                    
┏━━━━━━━━━━━━━━━━━┳━━━━━━━━━━┳━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━┓
┃ Security Group  ┃ Severity ┃ Live ENIs  ┃ Severed Workloads  ┃ Verdict       ┃
┡━━━━━━━━━━━━━━━━━╇━━━━━━━━━━╇━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━┩
│ sg-48b60281477… │ CRITICAL │ 3 direct   │ 3 ECS microservice │ BLOCK_PR_CRI… │
│                 │          │            │ tasks              │               │
└─────────────────┴──────────┴────────────┴────────────────────┴───────────────┘
```

---

### Scenario 2: Simulating CloudWatch FinOps Waste
```bash
# 1. Publish idle CloudWatch metrics (P99 CPU = 12.4%) to Floci
python simulate_finops_waste.py

# 2. Evaluate an instance upsize plan (t3.medium -> t3.xlarge)
terraform-mcp evaluate \
  --plan tests/fixtures/case_b_compute_upsize.json \
  --endpoint-url http://localhost:4566 \
  --markdown-out pr_report.md
```

#### Expected Output:
```text
╭──────────────────── Terraform MCP Pre-Merge Gate Report ─────────────────────╮
│ Verdict: BLOCK_PR_FINOPS_WASTE                                               │
│ Evaluation Latency: 118.20 ms                                                │
│ Topology Checks: 0 resource(s)                                               │
│ FinOps Checks: 1 resource(s)                                                 │
╰──────────────────────────────────────────────────────────────────────────────╯
                      FinOps Utilization & Waste Findings                       
┏━━━━━━━━━━━━━━━━━┳━━━━━━━━━┳━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━┓
┃ Resource ID     ┃ P99 CPU ┃   Compute Delta ┃ Monthly Waste ┃ Verdict        ┃
┡━━━━━━━━━━━━━━━━━╇━━━━━━━━━╇━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━┩
│ i-0987654321fe… │   12.4% │    t3.medium -> │    +$91.10/mo │ BLOCK_PR_FINO… │
│                 │         │       t3.xlarge │               │                │
└─────────────────┴─────────┴─────────────────┴───────────────┴────────────────┘
```

---

## 🔄 4. GitHub Actions Floci Simulation Workflow

For CI/CD testing in air-gapped or non-cloud connected environments, use [`.github/workflows/floci-simulation-gate.yml`](.github/workflows/floci-simulation-gate.yml):

```yaml
name: Floci Local Emulator Verification & Deployment Pipeline

on:
  pull_request:
    branches: [ floci, 'simulation/**' ]
  push:
    branches: [ floci, 'simulation/**' ]
  workflow_dispatch:
```

This workflow:
1. Automatically starts a `floci/floci:latest` Docker service in the GitHub Actions runner.
2. Injects live active microservice ENIs into Floci.
3. Evaluates the Terraform plan diff using FastMCP.
4. Posts the audit report directly on the PR and blocks dangerous merges.

---

## 🧹 5. Cleanup Floci Container

```bash
# Stop and remove Floci container
docker stop floci && docker rm floci
```
