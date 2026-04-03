# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Bedrock Budgeteer is a serverless AWS CDK application that monitors and controls AWS Bedrock API usage costs in real-time. It exclusively tracks Bedrock API keys (BedrockAPIKey- prefix) — not IAM users/roles/services. The system enforces per-user budgets through a progressive flow: warning → grace period → suspension → automatic restoration on budget refresh.

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
6. **CoreProcessingConstruct** — Lambda functions (usage_calculator, user_setup, budget_monitor, pricing_manager) with DLQs
7. **EventIngestionConstruct** — CloudTrail → EventBridge → Kinesis Firehose pipeline; Bedrock invocation log group with Lambda forwarder
8. **MonitoringConstruct** — CloudWatch dashboards, alarms, SNS topics (high_severity, operational_alerts, budget_alerts), multi-channel notifications
9. **WorkflowOrchestrationConstruct** — Step Functions state machines for suspension and restoration workflows

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
```

### Key Design Decisions

- **Pricing stored in DynamoDB** with daily refresh from AWS Pricing API + static fallbacks for Claude 4 models (not yet in Pricing API). Local 5-minute cache in `BedrockPricingCalculator`.
- **Suspension = detach AmazonBedrockLimitedAccess policy** (not deny policies). Restoration re-attaches it.
- **Lambda code is inline** — function implementations live in `constructs/lambda_functions/` and `constructs/workflow_lambda_functions/` as Python strings returned by `get_*_function_code()` functions.
- **Shared utilities** (`constructs/shared/`) are injected into Lambda code as layers/inline imports: `configuration_manager`, `dynamodb_helpers`, `metrics_publisher`, `lambda_utilities`, `event_publisher`, `pricing_calculator`.
- **Optional KMS encryption** — pass `--context kmsKeyArn=...` at deploy time; all constructs accept an optional `kms_key`.
- **Emergency controls were removed** — no maintenance mode or emergency stop (see CHANGELOG.md).

### Test Structure

Tests are in `app/tests/unit/`. They use `moto` for AWS service mocking and CDK assertions via `aws_cdk.assertions.Template.from_stack()`. Some tests skip with a note about a known CDK AspectLoop issue from the tagging framework.

### Configuration

Runtime config is via SSM parameters under `/bedrock-budgeteer/{environment}/{category}/{key}` and `/bedrock-budgeteer/global/{key}`. CDK context config is in `cdk.json` under `bedrock-budgeteer:config` and `bedrock-budgeteer:feature-flags`.
