# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Bedrock Budgeteer is a serverless AWS CDK application that monitors and controls AWS Bedrock API usage costs in real-time. It tracks Bedrock API keys (BedrockAPIKey- prefix) with pool-based budgets (global pool + per-key carve-outs by tier), and optionally tracks AgentCore runtimes. The system enforces budgets through a progressive flow: warning → grace period → suspension → automatic restoration on budget refresh. Keys can be provisioned via CDK with cost allocation tags, or detected automatically when created via IAM console (rogue key detection).

## Development Setup

All commands run from the `app/` directory:

```bash
cd app
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
```

Required environment variables for deployment:

```bash
export CDK_DEFAULT_ACCOUNT=<account-id>
export CDK_DEFAULT_REGION=us-east-1
```

## Common Commands

```bash
# All from app/ directory
python -m pytest tests/unit/ -v                    # Run all tests
python -m pytest tests/unit/test_core_processing.py -v  # Run single test file
python -m pytest tests/unit/ -v -k "test_name"     # Run single test by name
cdk synth                                          # Synthesize CloudFormation template
cdk diff                                           # Preview changes
cdk deploy                                         # Deploy stack
cdk destroy                                        # Tear down stack
```

## Architecture

### Stack Composition

`app.py` → `BedrockBudgeteerStack` (single "production" environment). The stack assembles these constructs in order:

1. **TaggingFramework** — CDK Aspect (`UnifiedTaggingAspect`) that auto-applies tags to all resources
2. **SecurityConstruct** — IAM roles (Lambda execution, Step Functions, EventBridge, Bedrock logging) and policies
3. **DataStorageConstruct** — 4 DynamoDB tables: user-budgets, usage-tracking, audit-logs, pricing
4. **LogStorageConstruct** — S3 bucket with lifecycle policies for log retention
5. **ConfigurationConstruct** — SSM Parameter Store hierarchy under `/bedrock-budgeteer/`
6. **CoreProcessingConstruct** — Lambda functions (user_setup, usage_calculator, budget_monitor, budget_refresh, audit_logger, state_reconciliation, pricing_manager) with DLQs
7. **EventIngestionConstruct** — CloudTrail → EventBridge → Kinesis Firehose pipeline; Bedrock invocation log group with Lambda forwarder
8. **MonitoringConstruct** — CloudWatch dashboards, alarms, SNS topics (high_severity, operational_alerts, budget_alerts), multi-channel notifications
9. **WorkflowOrchestrationConstruct** — Step Functions state machines for suspension and restoration workflows
10. **AgentCoreConstruct** — DynamoDB table, Lambda functions (agentcore_setup, agentcore_budget_monitor, agentcore_budget_manager with Function URL, agentcore_iam_utilities), EventBridge rules, Step Functions for AgentCore runtime suspension/restoration workflows
11. **CostAllocationReportingConstruct** — Daily Cost Explorer sync Lambda and cost reconciliation Lambda with CloudWatch dashboards. Feature-flagged via `enable_cost_allocation_reporting`.

**External tooling**: `manage_keys.py` — standalone CLI that provisions tagged IAM users (`BedrockAPIKey-{team}-{purpose}`) directly via AWS APIs. No CDK deploy needed.

### Data Flow

```
Bedrock API call → CloudTrail → EventBridge → Lambda (usage_calculator)
                                                  ↓
Bedrock invocation logs → CloudWatch → Lambda forwarder → Firehose → S3
                                                  ↓
DynamoDB (usage/budgets) ← cost calculation ← pricing from DynamoDB pricing table
         ↓
Budget Monitor (5-min schedule) → EventBridge → Step Functions
         ↓                                          ↓
   Suspension workflow                    Restoration workflow
   (grace notification → wait → detach policy)  (validate refresh → restore policy → reset budget)

AgentCore runtime lifecycle event → EventBridge → agentcore_setup → DynamoDB (agentcore-budgets)
Agent Bedrock API call → usage_calculator → role ARN match via GSI → agentcore-budgets table
agentcore_budget_monitor (5-min schedule) → suspension/restoration Step Functions

manage_keys.py add → IAM user + tags → CloudTrail → user_setup (budget registration)
IAM console key creation → CloudTrail → user_setup → auto-tag rogue key + SNS alert
Budget Monitor → 3-tier check: per-key → pool (GLOBAL_API_KEY_POOL) → global cap
Cost Explorer (daily) → cost_allocation_sync → CloudWatch metrics → Cost Allocation dashboard
```

### Key Design Decisions

- **Pricing stored in DynamoDB** with daily refresh from AWS Pricing API + static fallbacks for Claude 4 models (not yet in Pricing API). Local 5-minute cache in `BedrockPricingCalculator`.
- **Suspension = detach AmazonBedrockLimitedAccess policy** (not deny policies). Restoration re-attaches it.
- **Lambda code is inline** — function implementations live in `constructs/lambda_functions/` and `constructs/workflow_lambda_functions/` as Python strings returned by `get_*_function_code()` functions.
- **Shared utilities** (`constructs/shared/`) are concatenated into each function's inline `Code.from_inline()` source string (not Lambda Layers): `configuration_manager`, `dynamodb_helpers`, `metrics_publisher`, `lambda_utilities`, `event_publisher`, `pricing_calculator`.
- **Optional KMS encryption** — all constructs accept an optional `kms_key` parameter; pass the key through the stack constructor or CDK app configuration.
- **AgentCore suspension = snapshot + strip + deny-all** — unlike API key suspension (managed policy detach), AgentCore runtime suspension snapshots all role policies, strips them, attaches a deny-all inline policy, and tags the role. Restoration reverses the process: delete deny-all, reattach managed policies, recreate inline policies, untag, and reset budget.
- **Feature flag gating** — `enable_agentcore_budgeting`, `enable_key_provisioning`, and `enable_cost_allocation_reporting` in `cdk.json` feature flags control whether their respective constructs and runtime support are enabled.
- **Key provisioning is external** — `manage_keys.py` creates tagged IAM users directly via AWS APIs (no CDK deploy needed). The `enable_key_provisioning` flag gates the runtime support (SSM params, IAM permissions, SNS wiring) that the `user_setup` Lambda needs for tag detection and rogue key handling.
- **Pool-based API key budgets** — Global pool ($500 default) + per-key carve-outs by budget tier (low=$1, medium=$5, high=$25). Unbudgeted (rogue) keys draw from the pool. Global cap ($1000) acts as a guardrail across all keys. Mirrors the AgentCore budget model.
- **Rogue key auto-tagging** — Keys created outside `manage_keys.py` (e.g., via IAM console) are detected via CloudTrail, auto-tagged with default metadata, and trigger SNS alerts. They draw from the global pool with no carve-out.
- **Cost allocation tags** — `CostAllocation:Team` and `CostAllocation:Purpose` tags on IAM users enable AWS Cost Explorer grouping. `BedrockBudgeteer:*` tags are used for internal tracking.
- **Emergency controls were removed** — no maintenance mode or emergency stop (see CHANGELOG.md).

### Test Structure

Tests are in `app/tests/unit/`. They use `moto` for AWS service mocking and CDK assertions via `aws_cdk.assertions.Template.from_stack()`. Some tests skip with a note about a known CDK AspectLoop issue from the tagging framework.

### Configuration

Runtime config is via SSM parameters under `/bedrock-budgeteer/{environment}/{category}/{key}` and `/bedrock-budgeteer/global/{key}`. AgentCore parameters live under `/bedrock-budgeteer/global/agentcore/`. Key provisioning parameters are under `/bedrock-budgeteer/global/` (api_key_pool_budget_usd, budget_tier_low/medium/high_usd, api_key_global_cap_usd). CDK context config is in `cdk.json` under `bedrock-budgeteer:config` and `bedrock-budgeteer:feature-flags`.
