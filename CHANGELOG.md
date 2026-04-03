# Changelog

All notable changes to Bedrock Budgeteer are documented in this file.

## [Unreleased]

### Added
- AWS API Validation Audit: gap analysis of 22 discrepancies across CloudTrail events, pricing, IAM, and cost calculation
- CloudTrail advanced event selectors for Bedrock data events (agents, flows, knowledge bases, guardrails)
- EventBridge rules for new Bedrock operations: InvokeModelWithBidirectionalStream, InvokeInlineAgent, RetrieveAndGenerateStream, StartAsyncInvoke
- Fallback pricing for Claude 4.5/4.6 Opus, Sonnet 4.5/4.6, Haiku 4.5, Llama 4 Scout/Maverick, Mistral Large 2 (2407)
- Cross-region inference profile support for new prefixes (global, apac, au, ca, jp, us-gov) and providers (deepseek, google, qwen, writer, nvidia, openai, and others)
- Usage calculator routing for InvokeInlineAgent (uses foundationModel field), RetrieveAndGenerateStream, StartAsyncInvoke
- Comprehensive system documentation suite (architecture, deployment, API reference, diagrams)
- Bedrock Guardrails construct with content filtering and budget enforcement guardrails
- Native AWS/Bedrock CloudWatch metrics integration (invocations, tokens, latency, errors, images)
- Bedrock Agents, Flows, and Knowledge Bases monitoring on dashboard
- CloudWatch alarms for Bedrock throttles, server errors, and p99 latency

### Changed
- Automatic restoration flow: triggered by refresh period per API key (no manual approval)
- Simplified workflows: removed emergency override checks from suspension and restoration
- Budget monitor frequency reduced from 15 to 5 minutes
- Default grace period reduced from 300s to 60s in budget monitor logic

### Fixed
- Pricing API parser now filters by model ID instead of returning last matching price for any model (B7)
- Cache write token pricing corrected from 1.0x to 1.25x input rate for 5-min TTL prompt caching (S7)
- Claude 3.5 Sonnet v1 fallback pricing updated to extended access rate after March 2026 EOL (S8)
- Budget monitor Decimal-to-float conversion for `grace_deadline_epoch` from DynamoDB
- Step Functions DynamoDB timestamp: ISO strings no longer stored as numeric epoch values
- Grace period Lambda: passes actual SNS topic ARNs via environment variables instead of dynamic construction

### Removed
- Emergency controls (stop, maintenance mode, user whitelist)
- Emergency override Lambda function and related helpers
- Unused SSM parameters (emergency_stop_active, maintenance_mode, restoration_cooldown_hours, etc.)
- Unused `budget-alerts` DynamoDB table

## [v1.0.0] - Production Release

### Core System
- 4 DynamoDB tables: user-budgets, usage-tracking, audit-logs, pricing (all with auto-scaling)
- 7 core Lambda functions: user setup, usage calculator, budget monitor, budget refresh, audit logger, state reconciliation, pricing manager
- 4 workflow Lambda functions: IAM utilities, grace period notifications, policy backup, restoration validation
- 2 Step Functions state machines: suspension workflow, restoration workflow
- 3 SNS topics: operational alerts, budget alerts, high severity
- EventBridge rules for Bedrock API events (InvokeModel, Converse, etc.) and internal budget events
- Kinesis Firehose with Lambda data transformation for real-time cost calculation
- CloudWatch dashboard with native Bedrock metrics and system monitoring
- Bedrock Guardrails: content filtering (sexual, violence, hate, insults, misconduct, prompt attack) and PII anonymization

### Budget Enforcement
- Exclusive monitoring of Bedrock API keys (`BedrockAPIKey-` prefix)
- Progressive enforcement: warning (70%) → critical (90%) → grace period → suspension (100%)
- Suspension via `AmazonBedrockLimitedAccess` policy detachment
- Automatic restoration on budget refresh (daily check at 2 AM UTC)
- Configurable grace period, thresholds, and refresh period via SSM Parameter Store

### Pricing
- DynamoDB-based pricing table with daily refresh from AWS Bedrock API
- 50+ model pricing entries across Anthropic, Amazon, Meta, Mistral, Cohere, AI21, Stability
- Static fallback pricing for models not yet in AWS Pricing API (Claude 4 series)
- 5-minute local caching layer for optimal Lambda performance
- Batch inference 50% discount support

### Security & Compliance
- Least-privilege IAM roles for Lambda, Step Functions, EventBridge, Bedrock logging
- AWS-managed encryption by default, optional customer-managed KMS
- S3 buckets: public access blocked, SSL enforced, 30-day lifecycle
- Unified tagging framework via CDK Aspects (core, compliance, cost optimization tags)
- Complete audit trail in DynamoDB with structured event logging

### Configuration (SSM Parameter Store)
- `/bedrock-budgeteer/global/default_user_budget_usd` — $1 default
- `/bedrock-budgeteer/global/thresholds_percent_warn` — 70%
- `/bedrock-budgeteer/global/thresholds_percent_critical` — 90%
- `/bedrock-budgeteer/global/grace_period_seconds` — 300s
- `/bedrock-budgeteer/global/batch_inference_discount_percent` — 50%
- `/bedrock-budgeteer/production/cost/budget_refresh_period_days` — 30 days
- `/bedrock-budgeteer/production/monitoring/log_retention_days` — 7 days

### Infrastructure
- Single-environment architecture (production only, dev/staging removed)
- Modular CDK constructs: Security, DataStorage, LogStorage, Configuration, CoreProcessing, EventIngestion, Monitoring, WorkflowOrchestration, BedrockGuardrails, TaggingFramework
- All resources use `RemovalPolicy.DESTROY` for clean stack deletion
- Enterprise SCP compatibility via `skip-s3-public-access-block` feature flag

### Monitoring
- CloudWatch dashboard with native AWS/Bedrock metrics (invocations, tokens, latency, errors)
- Lambda monitoring: error rate, duration (p99), throttles per function
- DynamoDB monitoring: read/write capacity, throttles per table
- EventBridge monitoring: invocation counts, failed invocations per rule
- Firehose monitoring: delivery freshness and record counts
- SQS DLQ monitoring: queue depth alarms
- S3 monitoring: bucket size and object counts

## Development History

### Phase 1 — Foundation (2025-08-26)
DynamoDB tables, IAM security framework, monitoring stack, SSM configuration, tagging aspects, multi-environment support (later simplified to production-only).

### Phase 2 — Event Ingestion & Storage (2025-08-27)
CloudTrail integration, EventBridge rules, Kinesis Firehose streams, S3 log storage with lifecycle policies.

### Phase 3 — Core Processing (2025-08-27)
Lambda functions for user setup, usage calculation, budget monitoring, audit logging, state reconciliation. Shared utilities for configuration, DynamoDB helpers, pricing, metrics, and event publishing.

### Phase 4 — Workflow Orchestration (2025-08-27)
Step Functions suspension and restoration workflows. IAM utilities, grace period notifications, policy backup, restoration validation Lambda functions.

### Phase 5 — Notifications & Monitoring (2025-08-27)
Multi-channel SNS notifications, CloudWatch dashboards, comprehensive alarms across Lambda, DynamoDB, EventBridge, Firehose, SQS, and S3.

### Phase 6 — Operational Controls (2025-08-27)
DLQ management, retry strategies. Emergency controls were later removed as unnecessary.

### Phase 7 — Testing & Compliance (2025-08-30)
81 passing unit tests, CDK template synthesis validation, production deployment on AWS.

### Post-Phase Improvements
- Single-environment refactor (removed dev/staging)
- Encryption strategy update (AWS-managed default, optional KMS)
- DynamoDB pricing architecture (replaced direct Pricing API calls)
- Bedrock API key-only detection scope
- SSM parameter cleanup (82% reduction from ~50 to 9 parameters)
- Core processing modularization (81% file size reduction)
- Real-time Firehose data transformation
- Bedrock invocation logging support
- Bedrock Guardrails for content safety
- Native Bedrock CloudWatch metrics integration
