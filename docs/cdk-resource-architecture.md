---
title: CDK Resource Architecture
nav_order: 16
---

# CDK Resource Architecture

What exactly does `cdk deploy` create? This document inventories every AWS resource
the Bedrock Budgeteer stack provisions, how they connect to each other, and how the
system integrates with AWS Bedrock.

For the conceptual architecture and data flow diagrams, see
[System Architecture](system-architecture.md) and [System Diagrams](system-diagrams.md).

## Stack Overview

**Entry point:** `app/app.py` creates a single `BedrockBudgeteerStack` (environment: `production`).

The stack assembles up to 10 CDK constructs in strict dependency order (AgentCoreConstruct is feature-flagged):

```text
TaggingFramework          (CDK Aspect -- applies tags to everything below)
     |
SecurityConstruct         (IAM roles & policies)
     |
DataStorageConstruct      (DynamoDB tables)
     |
LogStorageConstruct       (S3 bucket)
     |
ConfigurationConstruct    (SSM parameters)
     |
CoreProcessingConstruct   (Lambda functions, DLQs, schedules)
     |                     depends on: tables, bucket, lambda role
EventIngestionConstruct   (CloudTrail, EventBridge, Firehose)
     |                     depends on: bucket, usage_calculator Lambda
MonitoringConstruct       (SNS, dashboards, alarms)
     |
WorkflowOrchestrationConstruct  (Step Functions, workflow Lambdas)
     |                     depends on: tables, core Lambdas, SF role, lambda role, SNS topics
AgentCoreConstruct            (DynamoDB, Lambdas, EventBridge, Step Functions)
                           depends on: lambda role, SF role, SNS topics
                           gated by: enable_agentcore_budgeting feature flag
```

After all constructs are created, the stack wires up cross-cutting concerns:

- Adds service-level permissions to the Lambda execution role (Bedrock, Pricing API,
  CloudTrail, SSM, IAM read, CloudWatch metrics, DynamoDB, S3, SQS).
- Creates monitoring for every Lambda, DLQ, table, trail, rule, Firehose stream,
  and state machine.
- Sets up notification channels (email, Slack, SMS, webhook) from environment variables.

## 1. TaggingFramework

**Source:** `app/app/constructs/tagging.py`

Creates no AWS resources directly. Registers a single CDK Aspect
(`UnifiedTaggingAspect`) that visits every CloudFormation resource at synth time
and applies tags in one pass.

### Core tags (all resources)

| Tag | Value |
|-----|-------|
| App | bedrock-budgeteer |
| Owner | `devops@company1.com` |
| Project | cost-management |
| CostCenter | engineering-ops |
| BillingProject | bedrock-budget-control |
| Environment | production |
| ManagedBy | cdk |
| Version | v1.0.0 |
| AutoShutdown | disabled |
| CostOptimization | conservative |
| ResourceTTL | permanent |

### Compliance tags (by resource type)

| Resource Type | Extra Tags |
|---------------|-----------|
| DynamoDB Table | `BackupRequired: true` |
| Lambda Function | `DataClassification: internal` |
| Step Functions State Machine | `DataClassification: internal`, `AuditTrail: enabled` |
| EventBridge Rule | `MonitoringLevel: standard` |
| KMS Key | `KeyRotation: enabled` |
| CloudWatch Log Group | `DataClassification: internal` |
| SNS Topic | `DataClassification: internal`, `NotificationLevel: operational` |

## 2. SecurityConstruct

**Source:** `app/app/constructs/security.py`

### IAM Roles (4)

| Role Name | Service Principal | Purpose |
|-----------|-------------------|---------|
| `bedrock-budgeteer-{env}-lambda-execution` | lambda.amazonaws.com | All Lambda functions share this role |
| `bedrock-budgeteer-{env}-step-functions` | states.amazonaws.com | Both Step Functions state machines |
| `bedrock-budgeteer-{env}-eventbridge` | events.amazonaws.com | EventBridge service role |
| `bedrock-budgeteer-{env}-bedrock-logging` | bedrock.amazonaws.com | Bedrock invocation logging to CloudWatch |

### Managed Policies (2)

| Policy Name | Grants |
|-------------|--------|
| `bedrock-budgeteer-{env}-dynamodb-access` | CRUD on all bedrock-budgeteer DynamoDB tables + GSIs |
| `bedrock-budgeteer-{env}-eventbridge-publish` | `events:PutEvents` to EventBridge |

### Permissions added later by the stack

The Lambda execution role receives additional inline policies after all constructs
are created:

- **Bedrock:** `ListFoundationModels`, `InvokeModel`
- **Pricing API:** `pricing:GetProducts`
- **CloudTrail:** Read access
- **SSM:** `GetParameter`, `GetParameters`, `GetParametersByPath`
- **IAM:** Read-only (`GetUser`, `ListAttachedUserPolicies`, etc.)
- **CloudWatch:** `PutMetricData`
- **DynamoDB:** Full access to all application tables
- **S3:** Read-only access to the logs bucket
- **SQS:** `SendMessage` to all DLQs

**Connects to:** Every other construct consumes roles from SecurityConstruct.

## 3. DataStorageConstruct

**Source:** `app/app/constructs/data_storage.py`

### DynamoDB Tables (4)

| Table | Partition Key | Sort Key | GSIs |
|-------|--------------|----------|------|
| `bedrock-budgeteer-{env}-user-budgets` | `principal_id` (S) | -- | `BudgetStatusIndex` (pk: `budget_status`, sk: `created_at`) |
| `bedrock-budgeteer-{env}-usage-tracking` | `principal_id` (S) | `timestamp` (S) | `ServiceUsageIndex` (pk: `service_name`, sk: `timestamp`) |
| `bedrock-budgeteer-{env}-audit-logs` | `event_id` (S) | `event_time` (S) | `UserAuditIndex` (pk: `user_identity`, sk: `event_time`), `EventSourceIndex` (pk: `event_source`, sk: `event_time`) |
| `bedrock-budgeteer-{env}-pricing` | `model_id` (S) | `region` (S) | -- |

### Provisioned capacity (per table)

| Table | Read Capacity | Write Capacity |
|-------|--------------|----------------|
| user-budgets | 5 | 5 |
| usage-tracking | 10 | 20 |
| audit-logs | 10 | 25 |
| pricing | 5 | 2 |

All tables auto-scale at 70% target utilization.

### Common table settings

| Setting | Value |
|---------|-------|
| Billing mode | PROVISIONED |
| Encryption | AWS-managed (or customer KMS if key provided) |
| Point-in-time recovery | Disabled (allows clean rollback) |
| Removal policy | DESTROY |

The **pricing** table uses a TTL attribute (`ttl`) so stale pricing entries
expire automatically.

**Connects to:** CoreProcessingConstruct and WorkflowOrchestrationConstruct
receive the `tables` dict. Every Lambda reads/writes these tables at runtime.

## 4. LogStorageConstruct

**Source:** `app/app/constructs/log_storage.py`

### S3 Buckets (1)

| Bucket | Purpose | Lifecycle |
|--------|---------|-----------|
| `bedrock-budgeteer-{env}-logs` | CloudTrail logs, Firehose output, error logs | Delete objects after 30 days |

### Configuration

| Setting | Value |
|---------|-------|
| Encryption | S3-managed (or KMS if key provided) |
| Versioning | Disabled |
| Block public access | BLOCK_ACLS (configurable via feature flag for enterprise SCPs) |
| Object ownership | BUCKET_OWNER_PREFERRED (allows CloudTrail ACL writes) |
| Auto-delete objects | true |
| Removal policy | DESTROY |

**Connects to:** Passed to CoreProcessingConstruct (Lambda env vars), EventIngestionConstruct
(CloudTrail destination, Firehose destination).

## 5. ConfigurationConstruct

**Source:** `app/app/constructs/configuration.py`

### SSM Parameters (6)

| Parameter Path | Default | Purpose |
|----------------|---------|---------|
| `/bedrock-budgeteer/{env}/cost/budget_refresh_period_days` | 30 | Days between budget resets |
| `/bedrock-budgeteer/{env}/monitoring/log_retention_days` | 7 | CloudWatch log retention |
| `/bedrock-budgeteer/global/thresholds_percent_warn` | 70 | Warning threshold % |
| `/bedrock-budgeteer/global/thresholds_percent_critical` | 90 | Critical threshold % |
| `/bedrock-budgeteer/global/default_user_budget_usd` | 1 | Default per-user budget (USD) |
| `/bedrock-budgeteer/global/grace_period_seconds` | 300 | Seconds before suspension after budget exceeded |

All parameters are `STANDARD` tier. Environment-scoped parameters include the
environment name in the path; global parameters are shared across environments.

**Connects to:** Lambda functions read these at runtime via the shared
`ConfigurationManager` utility. The monitoring log retention parameter name
is passed to MonitoringConstruct.

## 6. CoreProcessingConstruct

**Source:** `app/app/constructs/core_processing.py`

### Lambda Functions (7)

| Function Name | Memory | Timeout | Trigger | Purpose |
|---------------|--------|---------|---------|---------|
| `bedrock-budgeteer-user-setup-{env}` | 512 MB | 5 min | EventBridge (IAM key creation) | Initialize budget for new Bedrock API users |
| `bedrock-budgeteer-usage-calculator-{env}` | 1024 MB | 10 min | Firehose data transformation | Parse invocation logs, calculate token costs, update usage |
| `bedrock-budgeteer-budget-monitor-{env}` | 512 MB | 5 min | EventBridge schedule (every 5 min) | Check thresholds, start grace periods, trigger suspension |
| `bedrock-budgeteer-budget-refresh-{env}` | 512 MB | 5 min | EventBridge schedule (daily) | Reset budgets at refresh date, trigger auto-restoration |
| `bedrock-budgeteer-audit-logger-{env}` | 512 MB | 5 min | EventBridge (budgeteer events) | Write audit trail to DynamoDB |
| `bedrock-budgeteer-state-reconciliation-{env}` | 512 MB | 5 min | EventBridge schedule (every 4 hr) | Verify DynamoDB status matches actual IAM state |
| `bedrock-budgeteer-pricing-manager-{env}` | 512 MB | 5 min | EventBridge schedule (daily) | Refresh Bedrock model pricing from AWS Pricing API |

All functions use Python 3.11 runtime, share the Lambda execution role, and have
inline code generated from `app/app/constructs/lambda_functions/` and
`app/app/constructs/shared/lambda_utilities.py`.

### SQS Dead Letter Queues (6)

One DLQ per function (except pricing_manager):

```text
bedrock-budgeteer-{function_name}-dlq-{env}
```

- Retention: 14 days
- Visibility timeout: 5 minutes
- Encryption: KMS-managed

### Environment Variables (all functions)

| Variable | Source |
|----------|--------|
| `ENVIRONMENT` | Stack environment name |
| `USER_BUDGETS_TABLE` | DataStorageConstruct |
| `USAGE_TRACKING_TABLE` | DataStorageConstruct |
| `AUDIT_LOGS_TABLE` | DataStorageConstruct |
| `PRICING_TABLE` | DataStorageConstruct |
| `LOGS_BUCKET` | LogStorageConstruct |

**Connects to:** EventIngestionConstruct receives the `usage_calculator` function
for Firehose data transformation. WorkflowOrchestrationConstruct receives the full
`functions` dict.

## 7. EventIngestionConstruct

**Source:** `app/app/constructs/event_ingestion.py`

This construct builds the pipeline that captures Bedrock API activity and feeds
it into the processing layer.

### CloudTrail (1 trail)

| Resource | Configuration |
|----------|--------------|
| `bedrock-budgeteer-{env}-trail` | Multi-region, file validation enabled, CloudWatch Logs (30-day retention), management events capture Bedrock API calls |

### EventBridge Rules (3 -- rules only, no targets)

EventIngestionConstruct defines the rules and event patterns below, but does **not**
attach targets. Target wiring happens in `CoreProcessingConstruct._setup_event_routing()`.

| Rule | Event Pattern |
|------|--------------|
| `bedrock-budgeteer-{env}-bedrock-usage` | source: `aws.bedrock`, events: `InvokeModel`, `InvokeModelWithResponseStream`, `GetFoundationModel`, `ListFoundationModels` |
| `bedrock-budgeteer-{env}-iam-key-creation` | source: `aws.iam`, events: `CreateUser`, `CreateServiceSpecificCredential`, `AttachRolePolicy` |
| `bedrock-budgeteer-{env}-iam-bedrock-permissions` | source: `aws.iam`, events: `AttachUserPolicy`, `DetachUserPolicy`, `PutUserPolicy`, `DeleteUserPolicy` |

### Kinesis Data Firehose Streams (2)

| Stream | Destination | Buffer | Transformation |
|--------|------------|--------|----------------|
| `bedrock-budgeteer-{env}-usage-logs` | S3 (`bedrock-usage-logs/year=/month=/day=/hour=/`) | 5 MB / 300s, GZIP | usage_calculator Lambda |
| `bedrock-budgeteer-{env}-audit-logs` | S3 (`audit-logs/year=/month=/day=/hour=/`) | 3 MB / 60s, GZIP | None |

### CloudWatch Log Group (1) + Lambda Forwarder (1)

| Resource | Configuration |
|----------|--------------|
| `/aws/bedrock/bedrock-budgeteer-{env}-invocation-logs` | 7-day retention, KMS encryption (if key provided) |
| `bedrock-budgeteer-{env}-logs-forwarder` Lambda | Subscription filter on the log group, forwards to Firehose |

### How Bedrock connects in

```text
Bedrock API call
     |
     +---> CloudTrail (management event) ---> EventBridge rules
     |
     +---> Bedrock invocation logs ---> CloudWatch log group
                                             |
                                        Subscription filter
                                             |
                                        logs-forwarder Lambda
                                             |
                                        Firehose (usage-logs)
                                             |
                                        usage_calculator Lambda (transformation)
                                             |
                                     +-------+-------+
                                     |               |
                               DynamoDB tables    S3 (archive)
```

**Connects to:** Receives `s3_bucket` from LogStorageConstruct and
`usage_calculator_function` from CoreProcessingConstruct. Its trails, rules,
streams, and log groups are all passed to MonitoringConstruct for alarm creation.

## 8. MonitoringConstruct

**Source:** `app/app/constructs/monitoring.py`

### SNS Topics (3)

| Topic | Name | Purpose |
|-------|------|---------|
| operational_alerts | `bedrock-budgeteer-{env}-operational-alerts` | System operational issues |
| budget_alerts | `bedrock-budgeteer-{env}-budget-alerts` | Budget threshold violations |
| high_severity | `bedrock-budgeteer-{env}-high-severity` | Critical failures |

### Notification Channels (configured via environment variables)

| Channel | Env Variable | Topics |
|---------|-------------|--------|
| Email | `OPS_EMAIL` (or `cdk.json` `alert-email`) | All 3 topics |
| Slack | `SLACK_WEBHOOK_URL` | high_severity, operational_alerts |
| SMS | `OPS_PHONE_NUMBER` | high_severity |
| Webhook | `EXTERNAL_WEBHOOK_URL` | budget_alerts |

### CloudWatch Dashboards (3)

| Dashboard | Content |
|-----------|---------|
| `bedrock-budgeteer-{env}-system` | Lambda invocations/errors/duration, DynamoDB capacity, S3 objects |
| Ingestion pipeline dashboard | CloudTrail events, EventBridge rule metrics, Firehose delivery |
| Workflow dashboard | Step Functions executions, state machine errors |

### CloudWatch Alarms (per monitored resource)

| Alarm Pattern | Metric | Threshold | Notification |
|---------------|--------|-----------|-------------|
| `{function}-errors` | Lambda Errors | >= 1 in 5 min | high_severity |
| `{function}-duration` | Lambda Duration (p99) | >= 1000 ms | operational_alerts |
| `{table}-read-throttles` | DynamoDB ThrottledRequests | >= 5 | operational_alerts |
| `{trail}-errors` | CloudTrail ErrorCount | >= 1 | operational_alerts |
| `{rule}-failed` | EventBridge FailedInvocations | >= 1 | high_severity |
| `{stream}-delivery` | Firehose DataFreshness | >= 900s | operational_alerts |
| `{queue}-depth` | SQS MessageCount | >= 10 | operational_alerts |

### Custom Business Metrics (CloudWatch namespace: `BedrockBudgeteer`)

MonitoredUsers, BudgetExceededUsers, GracePeriodsStarted,
SuspensionWorkflowsTriggered, BudgetRefreshCompleted,
AutomaticRestorationsTriggered, AuditEventsProcessed, ReconciledUsers.

**Connects to:** Receives monitoring parameter name from ConfigurationConstruct.
SNS topics are passed to WorkflowOrchestrationConstruct for workflow notifications.

## 9. WorkflowOrchestrationConstruct

**Source:** `app/app/constructs/workflow_orchestration.py`

### Step Functions State Machines (2)

**Suspension Workflow** (`bedrock-budgeteer-suspension-{env}`, 30-min timeout):

```text
SendGraceNotification --> GracePeriodWait --> SendFinalWarning
     --> ApplyFullSuspension --> UpdateUserStatus --> Success
```

- Triggered by EventBridge when budget_monitor publishes `Suspension Workflow Required`
- **ApplyFullSuspension** detaches `AmazonBedrockLimitedAccess` managed policy from the IAM user

**Restoration Workflow** (`bedrock-budgeteer-restoration-{env}`, 10-min timeout):

```text
ValidateAutomaticRestoration --> [valid?]
     --> RestoreAccess --> ValidateAccessRestoration
     --> ResetBudgetStatus --> LogRestorationAudit
     --> SendRestorationNotification --> Success
```

- Triggered by EventBridge when budget_refresh publishes `Automatic User Restoration Required`
- **RestoreAccess** re-attaches `AmazonBedrockLimitedAccess` managed policy

### Workflow Lambda Functions (4)

| Function | Memory | Timeout | Purpose |
|----------|--------|---------|---------|
| `bedrock-budgeteer-iam-utilities-{env}` | 512 MB | 5 min | Detach/attach IAM policies, validate restrictions |
| `bedrock-budgeteer-grace-period-{env}` | 256 MB | 2 min | Send notifications via SNS (initial, final, restoration) |
| `bedrock-budgeteer-policy-backup-{env}` | 256 MB | 1 min | Backup/restore original IAM policies |
| `bedrock-budgeteer-restoration-validation-{env}` | 256 MB | 3 min | Check if refresh period has elapsed |

### Workflow DLQs (4)

One DLQ per workflow Lambda, same configuration as core DLQs.

### EventBridge Trigger Rules (2)

| Rule | Event Detail Type | Target |
|------|-------------------|--------|
| `bedrock-budgeteer-suspension-trigger-{env}` | `Suspension Workflow Required` | Suspension state machine |
| `bedrock-budgeteer-automatic-restoration-trigger-{env}` | `Automatic User Restoration Required` | Restoration state machine |

**Connects to:** Receives `dynamodb_tables`, `lambda_functions`, `step_functions_role`,
`lambda_execution_role`, and `sns_topics` from other constructs. The iam_utilities
Lambda gets additional IAM write permissions (attach/detach policies) beyond the
shared Lambda execution role.

## 10. AgentCoreConstruct

**Source:** `app/app/constructs/agentcore.py`

**Feature flag:** `enable_agentcore_budgeting` in `budgeteer.config.yaml`. This entire construct is only deployed when the flag is enabled.

### DynamoDB Tables (1)

| Table | Partition Key | Sort Key | GSIs |
|-------|--------------|----------|------|
| `bedrock-budgeteer-{env}-agentcore-budgets` | `runtime_id` (S) | -- | `role_arn-index` (pk: `role_arn`, sk: `runtime_id`) |

The table stores a `GLOBAL_POOL` singleton row for the total AgentCore spend pool and per-runtime rows for individual agent budget carve-outs.

### Lambda Functions (4)

| Function Name | Memory | Timeout | Trigger | Purpose |
|---------------|--------|---------|---------|---------|
| `bedrock-budgeteer-agentcore-setup-{env}` | 512 MB | 5 min | EventBridge (AgentCore lifecycle events) | Register new AgentCore runtimes, initialize per-agent budget carve-outs |
| `bedrock-budgeteer-agentcore-budget-monitor-{env}` | 512 MB | 5 min | EventBridge schedule (every 5 min) | Evaluate per-agent and global pool thresholds, trigger suspension/restoration |
| `bedrock-budgeteer-agentcore-budget-manager-{env}` | 512 MB | 5 min | Function URL (IAM auth) | API for managing agent budget allocations (CRUD) |
| `bedrock-budgeteer-agentcore-iam-utilities-{env}` | 512 MB | 5 min | Step Functions | Snapshot/strip/restore role policies, attach deny-all, tag/untag roles |

### SQS Dead Letter Queues (4)

One DLQ per Lambda function, same configuration as core DLQs (14-day retention, 5-min visibility timeout, KMS encryption).

### EventBridge Rules (2)

| Rule | Event Pattern / Schedule | Target |
|------|--------------------------|--------|
| `bedrock-budgeteer-{env}-agentcore-lifecycle` | source: `bedrock-agentcore.amazonaws.com` (lifecycle events) | agentcore_setup Lambda |
| `bedrock-budgeteer-{env}-agentcore-budget-monitor-schedule` | rate(5 minutes) | agentcore_budget_monitor Lambda |

### Step Functions State Machines (2)

**AgentCore Suspension Workflow:**

```text
SendGraceNotification --> GracePeriodWait --> SnapshotRolePolicies
     --> StripAllPolicies --> AttachDenyAll --> TagRole
     --> UpdateRuntimeStatus --> Success
```

- Suspension snapshots all role policies, strips them, attaches a deny-all inline policy, and tags the role with `BedrockBudgeteerManaged`

**AgentCore Restoration Workflow:**

```text
ValidateRestoration --> DeleteDenyAllPolicy --> ReattachManagedPolicies
     --> RecreateInlinePolicies --> UntagRole --> ResetBudget --> Success
```

### Function URL (1)

| Function | Auth Type | Purpose |
|----------|-----------|---------|
| `bedrock-budgeteer-agentcore-budget-manager-{env}` | IAM | HTTP API for agent budget management |

### IAM Permissions (scoped)

The agentcore_iam_utilities Lambda receives additional IAM permissions beyond the shared Lambda execution role:

- `iam:ListAttachedRolePolicies`, `iam:AttachRolePolicy`, `iam:DetachRolePolicy`
- `iam:PutRolePolicy`, `iam:DeleteRolePolicy`, `iam:ListRolePolicies`
- `iam:TagRole`, `iam:UntagRole`

All role management permissions are scoped to roles with the `BedrockBudgeteerManaged` tag.

### SSM Parameters (5)

| Parameter Path | Purpose |
|----------------|---------|
| `/bedrock-budgeteer/global/agentcore/global_budget_limit_usd` | Total AgentCore spend pool |
| `/bedrock-budgeteer/global/agentcore/grace_period_seconds` | Seconds before suspension |
| `/bedrock-budgeteer/global/agentcore/warning_threshold_percent` | Warning alert threshold |
| `/bedrock-budgeteer/global/agentcore/critical_threshold_percent` | Critical alert threshold |
| `/bedrock-budgeteer/global/agentcore/default_per_agent_budget_usd` | Default budget for new runtimes |

**Connects to:** The usage_calculator Lambda (CoreProcessingConstruct) performs an early routing
check: if the caller role ARN matches a registered AgentCore runtime via the `role_arn-index` GSI,
usage is tracked in the agentcore-budgets table. SecurityConstruct provides the Lambda execution
and Step Functions roles. MonitoringConstruct receives the AgentCore Lambdas, DLQs, and state
machines for alarm creation.

## End-to-End Integration Map

### Bedrock --> Budgeteer (usage capture)

```text
User calls Bedrock API (InvokeModel)
     |
     +--> CloudTrail captures management event
     |         |
     |         +--> EventBridge (bedrock-usage rule)
     |                   |
     |                   +--> Firehose (usage-logs) --> S3 archive
     |
     +--> Bedrock writes invocation log (tokens, model, latency)
               |
               +--> CloudWatch log group (/aws/bedrock/...)
                         |
                         +--> Subscription filter
                                   |
                                   +--> logs-forwarder Lambda
                                             |
                                             +--> Firehose (usage-logs)
                                                       |
                                                  usage_calculator Lambda
                                                       |
                                              +--------+--------+
                                              |                 |
                                        usage-tracking     user-budgets
                                        table (append)     table (update spent_usd)
```

### Budgeteer --> Bedrock Users (enforcement)

```text
budget_monitor Lambda (every 5 min)
     |
     +--> Scans user-budgets table
     |
     +--> spent_usd >= budget_limit_usd?
               |
          [yes]--> Grace period already started?
               |         |
               |    [no]--> Set grace_deadline_epoch, publish "Grace Period Started"
               |         |
               |    [yes, expired]--> Publish "Suspension Workflow Required"
               |                           |
               |                      EventBridge --> Step Functions
               |                           |
               |                      Grace notification (SNS)
               |                           |
               |                      Wait (grace_period_seconds)
               |                           |
               |                      Final warning (SNS)
               |                           |
               |                      iam_utilities Lambda:
               |                        Detach AmazonBedrockLimitedAccess
               |                           |
               |                      Update user-budgets: status = "suspended"
               |
budget_refresh Lambda (daily)
     |
     +--> Scans suspended users where refresh date reached
     |
     +--> Publishes "Automatic User Restoration Required"
               |
          EventBridge --> Step Functions
               |
          Validate eligibility --> Attach AmazonBedrockLimitedAccess
               |
          Reset spent_usd = 0, status = "active"
               |
          Restoration notification (SNS)
```

### CDK deploy-time vs. Lambda runtime

At **deploy time**, CDK constructs wire AWS services together: IAM roles are
assigned to Lambdas, table names are injected as environment variables,
EventBridge rules are created with targets, Firehose is configured with the
usage_calculator as its data transformer.

At **runtime**, Lambda functions use shared utilities that are concatenated into
each function's `Code.from_inline()` source string (not Lambda Layers).
The utilities (`app/app/constructs/shared/lambda_utilities.py`) bundle:

- `ConfigurationManager` -- reads SSM parameters with local caching
- `DynamoDBHelper` -- Decimal/float conversion for DynamoDB
- `BedrockPricingCalculator` -- pricing lookup with 5-min local cache + DynamoDB + AWS Pricing API fallback chain
- `MetricsPublisher` -- publishes custom CloudWatch metrics
- `EventPublisher` -- publishes events to EventBridge for cross-Lambda communication

## Resource Naming Convention

Resources use two naming patterns depending on service:

```text
bedrock-budgeteer-{environment}-{component}   (tables, SNS, trails, Firehose, S3)
bedrock-budgeteer-{component}-{environment}   (Lambdas, DLQs, Step Functions)
```

| Resource Type | Example |
|---------------|---------|
| DynamoDB table | `bedrock-budgeteer-production-user-budgets` |
| Lambda function | `bedrock-budgeteer-usage-calculator-production` |
| SQS DLQ | `bedrock-budgeteer-user_setup-dlq-production` |
| SNS topic | `bedrock-budgeteer-production-operational-alerts` |
| CloudTrail trail | `bedrock-budgeteer-production-trail` |
| EventBridge rule | `bedrock-budgeteer-production-bedrock-usage` |
| Firehose stream | `bedrock-budgeteer-production-usage-logs` |
| Step Functions | `bedrock-budgeteer-suspension-production` |
| S3 bucket | `bedrock-budgeteer-production-logs` |
| SSM parameter | `/bedrock-budgeteer/production/cost/budget_refresh_period_days` |

## Resource Count Summary

| AWS Service | Count | Resources |
|-------------|-------|-----------|
| DynamoDB Tables | 4 (+1 if AgentCore) | user-budgets, usage-tracking, audit-logs, pricing (+agentcore-budgets) |
| Lambda Functions | 12+ (+4 if AgentCore) | 7 core + 4 workflow + 1 logs-forwarder (+ conditional Slack/webhook Lambdas if env vars set) (+4 AgentCore) |
| SQS Queues (DLQs) | 10 (+4 if AgentCore) | 6 core + 4 workflow (+4 AgentCore) |
| IAM Roles | 4 | lambda-execution, step-functions, eventbridge, bedrock-logging |
| IAM Managed Policies | 2 | dynamodb-access, eventbridge-publish |
| S3 Buckets | 1 | logs |
| SNS Topics | 3 | operational-alerts, budget-alerts, high-severity |
| CloudTrail Trails | 1 | trail |
| EventBridge Rules | 5+ (+2 if AgentCore) | 3 ingestion + 2 workflow triggers + schedules (+2 AgentCore) |
| Firehose Streams | 2 | usage-logs, audit-logs |
| Step Functions | 2 (+2 if AgentCore) | suspension, restoration (+AgentCore suspension, AgentCore restoration) |
| CloudWatch Dashboards | 3 | system, ingestion-pipeline, workflow |
| CloudWatch Alarms | ~20+ | Per Lambda, table, trail, rule, stream, and DLQ |
| SSM Parameters | 6 (+5 if AgentCore) | 2 env-scoped + 4 global (+5 AgentCore global) |
| CloudWatch Log Groups | 1+ | Bedrock invocation logs (+ Lambda runtime-created function log groups) |
| Function URLs | 0 (+1 if AgentCore) | AgentCore budget manager (IAM auth) |
