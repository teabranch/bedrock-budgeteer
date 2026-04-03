---
title: Home
nav_order: 0
permalink: /
---

# Bedrock Budgeteer

A comprehensive serverless budget monitoring and control system for AWS Bedrock API usage.

<p><em>Find this useful? Star the repo to follow updates and show support!</em>
<a href="https://github.com/teabranch/bedrock-budgeteer" title="Star Bedrock Budgeteer on GitHub" style="display: inline-block; vertical-align: middle; padding: 6px 12px; border: 1px solid #d0d7de; border-radius: 6px; text-decoration: none;">⭐ Star on GitHub</a></p>

> **Deploy with CDK** — `cdk deploy` from the `app/` directory.
> See [Deployment Guide](docs/deployment-guide.md) for all options.

Bedrock Budgeteer monitors every Bedrock API call in real-time, calculates token-based costs, and enforces per-user budgets through a progressive flow: warning, grace period, suspension, and automatic restoration on budget refresh.

---

## What's Inside

- **[System Architecture](docs/system-architecture.md)** — Stack composition, data flow, and key design decisions
- **[System Diagrams](docs/system-diagrams.md)** — Visual architecture and sequence diagrams
- **[Deployment Guide](docs/deployment-guide.md)** — Quick start deployment instructions
- **[Comprehensive Deployment](docs/comprehensive-deployment-guide.md)** — Full deployment walkthrough with all options
- **[Enterprise Deployment](docs/enterprise-deployment-guide.md)** — Multi-account and enterprise setup
- **[CDK Bootstrap](docs/cdk-bootstrap-guide.md)** — CDK bootstrapping for your AWS account
- **[API Reference](docs/api-reference.md)** — Lambda functions, DynamoDB schemas, and SSM parameters
- **[Testing Strategy](docs/testing-strategy.md)** — Test structure, running tests, and coverage
- **[Cost Optimization](docs/cost-optimization-guide.md)** — Minimizing operational costs
- **[IAM Policy Templates](docs/iam-policy-templates.md)** — Ready-to-use IAM policies
- **[KMS Setup](docs/kms-setup-guide.md)** — Customer-managed encryption key configuration
- **[SSM Parameters](docs/ssm-parameter-hierarchy.md)** — Parameter Store hierarchy reference
- **[Naming Conventions](docs/naming-conventions.md)** — Resource naming standards
- **[Tagging Framework](docs/tagging-framework.md)** — Automated resource tagging implementation
- **[Tagging Strategy](docs/tagging-strategy.md)** — Tag taxonomy and governance

---

## Key Features

- **Real-time cost tracking** — Monitors every Bedrock API call and calculates token-based costs using the AWS Pricing API
- **Automated budget enforcement** — Per-user spending limits with progressive controls (warnings, grace period, suspension)
- **Smart notifications** — Multi-channel alerts via email, Slack, and SMS
- **Zero-touch operation** — Fully serverless with automatic user setup and budget initialization
- **Enterprise-ready** — Comprehensive audit trails, IAM-based access control, optional KMS encryption

---

## Quick Start

### Prerequisites

- Python 3.11+, Node.js 18+, AWS CDK CLI v2, AWS CLI v2
- AWS account with CDK bootstrapped

### Deploy

```bash
cd app
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cdk deploy
```

### Verify

```bash
python -m pytest tests/unit/ -v
```

---

## About

Bedrock Budgeteer is an open-source project by [TEA/Branch](https://teabranch.dev).

Licensed under [MIT](https://github.com/teabranch/bedrock-budgeteer/blob/main/LICENSE).
