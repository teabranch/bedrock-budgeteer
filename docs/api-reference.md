# API Reference - Bedrock Budgeteer

## Overview

This document provides comprehensive API reference for all constructs, classes, and interfaces in the Bedrock Budgeteer system. This reference is intended for developers extending or maintaining the system.

## CDK Constructs

### BedrockBudgeteerStack

Main application stack that orchestrates all system components.

**Constructor:**
```python
BedrockBudgeteerStack(
    scope: Construct,
    construct_id: str,
    environment_name: str = "production",
    kms_key: Optional[kms.IKey] = None,
    **kwargs
)
```

**Parameters:**
- `scope`: CDK construct scope
- `construct_id`: Unique identifier for the stack
- `environment_name`: Environment name (default: "production")
- `kms_key`: Optional customer-managed KMS key for encryption

**Properties:**
```python
@property
def dynamodb_tables(self) -> Dict[str, dynamodb.Table]
    """Expose DynamoDB tables for use by other constructs"""

@property 
def iam_roles(self) -> Dict[str, iam.Role]
    """Expose IAM roles for use by other constructs"""

@property
def sns_topics(self) -> Dict[str, sns.Topic]
    """Expose SNS topics for use by other constructs"""

@property
def lambda_functions(self) -> Dict[str, lambda_.Function]
    """Expose Lambda functions for use by other constructs"""

@property
def step_functions_state_machines(self) -> Dict[str, sfn.StateMachine]
    """Expose Step Functions state machines"""
```

**Usage Example:**
```python
from app.app_stack import BedrockBudgeteerStack

stack = BedrockBudgeteerStack(
    app, "BedrockBudgeteer",
    environment_name="production",
    env=cdk.Environment(account="123456789012", region="us-east-1")
)
```

### DataStorageConstruct

Manages DynamoDB tables and data storage resources.

**Constructor:**
```python
DataStorageConstruct(
    scope: Construct,
    construct_id: str,
    environment_name: str,
    kms_key: Optional[kms.IKey] = None,
    **kwargs
)
```

**Tables Created:**
- `user_budgets`: User budget tracking table
- `usage_tracking`: Usage and cost tracking table  
- `audit_logs`: System audit trail table
- `pricing`: Bedrock model pricing cache table

**Properties:**
```python
@property
def tables(self) -> Dict[str, dynamodb.Table]
    """Dictionary of created DynamoDB tables"""
```

**Table Schemas:**

**UserBudgets Table:**
```python
{
    "partition_key": "principal_id",  # String
    "attributes": {
        "budget_limit_usd": "Number",
        "spent_usd": "Number", 
        "status": "String",  # active|suspended|grace_period
        "account_type": "String",  # bedrock_api_key|user|service
        "budget_refresh_date": "String",  # ISO8601
        "grace_deadline_epoch": "Number"
    },
    "gsi": {
        "BudgetStatusIndex": {
            "partition_key": "budget_status",
            "sort_key": "created_at"
        }
    }
}
```

**UsageTracking Table:**
```python
{
    "partition_key": "principal_id",  # String
    "sort_key": "timestamp",  # String
    "attributes": {
        "service_name": "String",
        "cost_usd": "Number",
        "token_count": "Number",
        "model_id": "String"
    },
    "gsi": {
        "ServiceUsageIndex": {
            "partition_key": "service_name",
            "sort_key": "timestamp"
        }
    }
}
```

### SecurityConstruct

Manages IAM roles, policies, and security resources.

**Constructor:**
```python
SecurityConstruct(
    scope: Construct,
    construct_id: str,
    environment_name: str,
    **kwargs
)
```

**Roles Created:**
- `lambda_execution`: Execution role for Lambda functions
- `step_functions`: Execution role for Step Functions
- `eventbridge`: Service role for EventBridge
- `bedrock_logging`: Role for Bedrock invocation logging

**Properties:**
```python
@property
def roles(self) -> Dict[str, iam.Role]
    """Dictionary of created IAM roles"""

@property
def policies(self) -> Dict[str, iam.ManagedPolicy] 
    """Dictionary of created managed policies"""

@property
def bedrock_logging_role(self) -> iam.Role
    """Bedrock logging role for console configuration"""

@property
def lambda_execution_role(self) -> iam.Role
    """Lambda execution role for additional permissions"""
```

**Methods:**
```python
def add_bedrock_permissions(self) -> None
    """Add Bedrock API permissions for cost monitoring"""

def add_pricing_api_permissions(self) -> None
    """Add AWS Pricing API permissions for cost calculation"""

def add_cloudtrail_permissions(self) -> None
    """Add CloudTrail permissions for usage tracking"""

def add_ssm_permissions(self) -> None
    """Add SSM Parameter Store permissions"""

def add_dynamodb_permissions(self, tables: Dict[str, Any]) -> None
    """Add DynamoDB permissions for Lambda functions"""

def create_policy_template(self, service_name: str, actions: List[str], 
                          resources: List[str]) -> iam.ManagedPolicy
    """Create a reusable policy template for any AWS service"""
```

### EventIngestionConstruct

Manages CloudTrail, EventBridge, and Kinesis Data Firehose for event collection.

**Constructor:**
```python
EventIngestionConstruct(
    scope: Construct,
    construct_id: str,
    environment_name: str,
    s3_bucket: Optional[s3.Bucket] = None,
    kms_key: Optional[kms.IKey] = None,
    usage_calculator_function: Optional[lambda_.Function] = None,
    **kwargs
)
```

**Properties:**
```python
@property
def cloudtrail_trails(self) -> Dict[str, cloudtrail.Trail]
    """Dictionary of CloudTrail trails"""

@property
def eventbridge_rules(self) -> Dict[str, events.Rule]
    """Dictionary of EventBridge rules"""

@property 
def firehose_streams(self) -> Dict[str, firehose.DeliveryStream]
    """Dictionary of Kinesis Firehose streams"""

@property
def log_groups(self) -> Dict[str, logs.LogGroup]
    """Dictionary of CloudWatch log groups"""

@property
def bedrock_invocation_log_group(self) -> logs.LogGroup
    """Bedrock invocation log group for configuration"""
```

**Methods:**
```python
def add_eventbridge_target(self, rule_name: str, target) -> None
    """Add a target to an existing EventBridge rule"""

def configure_usage_calculator(self, usage_calculator_function: lambda_.Function) -> None
    """Configure usage calculator Lambda for real-time processing"""
```

### CoreProcessingConstruct

Implements Lambda functions for processing events, calculating costs, and monitoring budgets.

**Constructor:**
```python
CoreProcessingConstruct(
    scope: Construct,
    construct_id: str,
    environment_name: str,
    dynamodb_tables: Dict[str, dynamodb.Table],
    s3_bucket: s3.Bucket,
    lambda_execution_role: iam.Role,
    kms_key: Optional[kms.Key] = None,
    **kwargs
)
```

**Properties:**
```python
@property
def functions(self) -> Dict[str, lambda_.Function]
    """Dictionary of Lambda functions"""

@property
def dead_letter_queues(self) -> Dict[str, sqs.Queue]
    """Dictionary of DLQ queues for monitoring"""

@property
def execution_role(self) -> iam.Role
    """Execution role for additional permissions"""
```

**Lambda Functions Created:**
- `user_setup`: Initialize budgets from CloudTrail events
- `usage_calculator`: Transform Bedrock logs into cost records
- `budget_monitor`: Evaluate thresholds and trigger workflows
- `budget_refresh`: Reset budgets and restore users
- `audit_logger`: Process audit events
- `state_reconciliation`: Verify IAM/DynamoDB consistency
- `pricing_manager`: Manage Bedrock pricing data

### WorkflowOrchestrationConstruct

Coordinates suspension and restoration workflows using Step Functions.

**Constructor:**
```python
WorkflowOrchestrationConstruct(
    scope: Construct,
    construct_id: str,
    environment_name: str,
    dynamodb_tables: Dict[str, dynamodb.Table],
    lambda_functions: Dict[str, lambda_.Function],
    step_functions_role: iam.Role,
    lambda_execution_role: iam.Role,
    sns_topics: Optional[Dict[str, sns.Topic]] = None,
    kms_key: Optional[kms.Key] = None,
    **kwargs
)
```

**Properties:**
```python
@property
def suspension_state_machine(self) -> sfn.StateMachine
    """Suspension workflow state machine"""

@property
def restoration_state_machine(self) -> sfn.StateMachine
    """Restoration workflow state machine"""

@property
def workflow_functions(self) -> Dict[str, lambda_.Function]
    """Dictionary of workflow Lambda functions"""

@property
def workflow_dlqs(self) -> Dict[str, sqs.Queue]
    """Dictionary of workflow DLQ queues"""

@property
def state_machines(self) -> Dict[str, sfn.StateMachine]
    """Dictionary of all state machines"""
```

**Workflow Functions Created:**
- `iam_utilities`: IAM policy management utilities
- `grace_period`: Grace period notifications
- `policy_backup`: Policy backup operations
- `restoration_validation`: Restoration eligibility validation

### MonitoringConstruct

Manages CloudWatch resources, dashboards, and alarms.

**Constructor:**
```python
MonitoringConstruct(
    scope: Construct,
    construct_id: str,
    environment_name: str,
    **kwargs
)
```

**Properties:**
```python
@property
def topics(self) -> Dict[str, sns.Topic]
    """Dictionary of SNS topics"""

@property
def alarms(self) -> Dict[str, cloudwatch.Alarm]
    """Dictionary of CloudWatch alarms"""

@property
def log_groups(self) -> Dict[str, logs.LogGroup]
    """Dictionary of log groups"""
```

**Methods:**
```python
def add_lambda_monitoring(self, function_name: str, lambda_function) -> None
    """Add monitoring for a Lambda function"""

def add_dynamodb_monitoring(self, table_name: str, table) -> None
    """Add monitoring for a DynamoDB table"""

def add_stepfunctions_monitoring(self, state_machine_name: str, state_machine) -> None
    """Add monitoring for Step Functions state machines"""

def add_email_subscription(self, topic_name: str, email: str) -> None
    """Add email subscription to SNS topic"""

def add_slack_subscription(self, topic_name: str, webhook_url: str) -> None
    """Add Slack webhook subscription to SNS topic"""

def create_custom_business_metrics(self) -> None
    """Create custom CloudWatch metrics for business monitoring"""
```

**SNS Topics Created:**
- `operational_alerts`: System operational issues
- `budget_alerts`: Budget threshold violations  
- `high_severity`: Critical system alerts

### ConfigurationConstruct

Manages SSM Parameter Store hierarchy and application configuration.

**Constructor:**
```python
ConfigurationConstruct(
    scope: Construct,
    construct_id: str,
    environment_name: str,
    kms_key: Optional[kms.Key] = None,
    **kwargs
)
```

**Properties:**
```python
@property
def parameters(self) -> Dict[str, ssm.StringParameter]
    """Dictionary of created SSM parameters"""
```

**Methods:**
```python
def get_parameter_reference(self, category: str, key: str) -> str
    """Get SSM parameter reference for use in other constructs"""

def create_custom_parameter(self, category: str, key: str, value: str,
                          description: str, secure: bool = False) -> ssm.StringParameter
    """Create a custom parameter in the hierarchy"""
```

**Parameter Hierarchy:**
```
/bedrock-budgeteer/
├── global/
│   ├── thresholds_percent_warn
│   ├── thresholds_percent_critical  
│   ├── default_user_budget_usd
│   └── grace_period_seconds
└── production/
    └── cost/
        └── budget_refresh_period_days
```

## Workflow Classes

### SuspensionWorkflow

Defines the Step Functions state machine for user suspension workflow.

**Constructor:**
```python
SuspensionWorkflow(
    scope: Construct,
    environment_name: str,
    dynamodb_tables: Dict[str, dynamodb.Table],
    workflow_lambda_functions: Dict[str, lambda_.Function],
    step_functions_role: iam.Role
)
```

**Methods:**
```python
def create_suspension_workflow(self) -> sfn.StateMachine
    """Create Step Functions state machine for user suspension workflow"""
```

**Workflow Steps:**
1. Send Grace Notification
2. Grace Period Wait (configurable duration)
3. Send Final Warning
4. Apply Full Suspension
5. Update User Status
6. Send Audit Event

### RestorationWorkflow

Defines the Step Functions state machine for user restoration workflow.

**Constructor:**
```python
RestorationWorkflow(
    scope: Construct,
    environment_name: str,
    dynamodb_tables: Dict[str, dynamodb.Table],
    workflow_lambda_functions: Dict[str, lambda_.Function],
    step_functions_role: iam.Role
)
```

**Methods:**
```python
def create_restoration_workflow(self) -> sfn.StateMachine
    """Create Step Functions state machine for user restoration workflow"""
```

**Workflow Steps:**
1. Validate Automatic Restoration
2. Validation Choice
3. Restore Access (if validated)
4. Validate Access Restoration
5. Reset Budget Status
6. Send Audit Event

### WorkflowBase

Base class for workflow definitions with common utilities.

**Methods:**
```python
def create_lambda_invoke_task(self, task_name: str, function_key: str, 
                            input_data: Dict, result_path: str) -> sfn_tasks.LambdaInvoke
    """Create a Lambda invoke task with error handling"""

def create_dynamodb_update_task(self, task_name: str, table_key: str,
                              key: Dict, update_expression: str,
                              expression_attribute_names: Dict,
                              expression_attribute_values: Dict,
                              result_path: str) -> sfn_tasks.DynamoUpdateItem
    """Create a DynamoDB update task"""

def create_failure_state(self, state_name: str, error: str, cause: str) -> sfn.Fail
    """Create a failure state for error handling"""
```

## Shared Utilities

### ConfigurationManager

Manages SSM parameter configuration with caching.

**Methods:**
```python
@classmethod
def get_parameter(cls, parameter_name: str, default_value: Any = None) -> Any
    """Get parameter from SSM Parameter Store with caching"""

@classmethod  
def get_budget_thresholds(cls) -> Dict[str, float]
    """Get budget threshold configuration"""
```

### DynamoDBHelper

Helper functions for DynamoDB operations.

**Methods:**
```python
@staticmethod
def decimal_to_float(obj) -> Any
    """Convert Decimal objects to float for JSON serialization"""

@staticmethod
def float_to_decimal(obj) -> Any
    """Convert float objects to Decimal for DynamoDB storage"""

@staticmethod
def get_user_budget(principal_id: str) -> Optional[Dict]
    """Get user budget record from DynamoDB"""

@staticmethod
def update_user_budget(principal_id: str, spent_usd: float) -> bool
    """Update user budget spent amount"""
```

### BedrockPricingCalculator

Calculates costs for Bedrock API usage.

**Methods:**
```python
@staticmethod
def calculate_cost(model_id: str, input_tokens: int, output_tokens: int, 
                  region: str = "us-east-1") -> float
    """Calculate cost for Bedrock API usage"""

@staticmethod
def fetch_pricing_from_api(model_id: str, region: str) -> Optional[Dict]
    """Fetch current pricing from AWS Pricing API"""

@staticmethod
def get_cached_pricing(model_id: str, region: str) -> Optional[Dict]
    """Get pricing from DynamoDB cache"""
```

### MetricsPublisher

Publishes custom CloudWatch metrics.

**Methods:**
```python
@staticmethod
def publish_budget_metric(metric_name: str, value: float, unit: str, 
                         dimensions: Dict[str, str]) -> None
    """Publish a budget-related metric to CloudWatch"""

@staticmethod
def publish_system_metric(metric_name: str, value: float, unit: str,
                         dimensions: Dict[str, str]) -> None
    """Publish a system-related metric to CloudWatch"""
```

### EventPublisher

Publishes events to EventBridge.

**Methods:**
```python
@staticmethod
def publish_budget_event(event_type: str, detail: Dict[str, Any]) -> None
    """Publish a budget-related event to EventBridge"""

@staticmethod
def publish_audit_event(event_type: str, detail: Dict[str, Any]) -> None
    """Publish an audit event to EventBridge"""
```

## Lambda Function APIs

### User Setup Lambda

Initializes budget entries for new users.

**Event Input:**
```json
{
  "detail": {
    "eventName": "CreateUser",
    "responseElements": {
      "user": {
        "userName": "BedrockAPIKey-UserName"
      }
    }
  }
}
```

**Response:**
```json
{
  "statusCode": 200,
  "principal_id": "BedrockAPIKey-UserName",
  "budget_initialized": true,
  "budget_limit_usd": 1.0
}
```

### Usage Calculator Lambda

Processes Bedrock invocation logs and calculates costs.

**Event Input (Firehose):**
```json
{
  "records": [
    {
      "data": "base64-encoded-log-event"
    }
  ]
}
```

**Response:**
```json
{
  "records": [
    {
      "recordId": "string",
      "result": "Ok",
      "data": "base64-encoded-transformed-data"
    }
  ]
}
```

### Budget Monitor Lambda

Evaluates budget thresholds and triggers suspension workflows.

**Event Input (Scheduled):**
```json
{
  "source": "aws.events",
  "detail-type": "Scheduled Event"
}
```

**Response:**
```json
{
  "statusCode": 200,
  "monitored_users": 25,
  "budget_exceeded_users": 2
}
```

### Pricing Manager Lambda

Manages Bedrock model pricing data.

**Event Input:**
```json
{
  "action": "daily_refresh"
}
```

**Response:**
```json
{
  "statusCode": 200,
  "body": {
    "refreshed": 15,
    "total": 20,
    "failed": 5,
    "populated_by": "populated by event"
  }
}
```

## Error Handling

### Standard Error Response

All Lambda functions return standardized error responses:

```json
{
  "statusCode": 500,
  "error": "Error description",
  "details": {
    "function": "function-name",
    "timestamp": "2024-01-01T00:00:00Z",
    "request_id": "uuid"
  }
}
```

### Dead Letter Queue Format

Failed Lambda executions are sent to DLQ with metadata:

```json
{
  "original_event": {},
  "error_message": "string",
  "function_name": "string", 
  "timestamp": "ISO8601",
  "attempt_count": 3
}
```

## Environment Variables

### Lambda Function Environment Variables

All Lambda functions receive these standard environment variables:

```python
{
  "ENVIRONMENT": "production",
  "USER_BUDGETS_TABLE": "bedrock-budgeteer-production-user-budgets",
  "USAGE_TRACKING_TABLE": "bedrock-budgeteer-production-usage-tracking", 
  "AUDIT_LOGS_TABLE": "bedrock-budgeteer-production-audit-logs",
  "PRICING_TABLE": "bedrock-budgeteer-production-pricing",
  "LOGS_BUCKET": "bedrock-budgeteer-production-logs"
}
```

### Workflow-Specific Environment Variables

Workflow Lambda functions receive additional variables:

```python
{
  "HIGH_SEVERITY_TOPIC_ARN": "arn:aws:sns:...",
  "OPERATIONAL_ALERTS_TOPIC_ARN": "arn:aws:sns:...",
  "BUDGET_ALERTS_TOPIC_ARN": "arn:aws:sns:..."
}
```

## Event Schemas

### EventBridge Event Schemas

**Budget Violation Event:**
```json
{
  "source": "bedrock-budgeteer",
  "detail-type": "Suspension Workflow Required",
  "detail": {
    "principal_id": "string",
    "reason": "grace_period_expired",
    "grace_period_seconds": 300,
    "budget_data": {
      "account_type": "bedrock_api_key",
      "budget_limit_usd": 10.0,
      "spent_usd": 12.5,
      "budget_usage_percent": 125.0
    },
    "triggered_by": "budget_monitor",
    "timestamp": "2024-01-01T00:00:00Z"
  }
}
```

**Restoration Event:**
```json
{
  "source": "bedrock-budgeteer",
  "detail-type": "Automatic User Restoration Required",
  "detail": {
    "principal_id": "string",
    "restoration_reason": "budget_refresh_period_reached",
    "refresh_date": "2024-01-01T00:00:00Z",
    "current_time": "2024-01-01T00:00:00Z"
  }
}
```

## Configuration Reference

### SSM Parameter Reference

**Global Parameters:**
```
/bedrock-budgeteer/global/thresholds_percent_warn = "70"
/bedrock-budgeteer/global/thresholds_percent_critical = "90"
/bedrock-budgeteer/global/default_user_budget_usd = "1"
/bedrock-budgeteer/global/grace_period_seconds = "300"
```

**Environment-Specific Parameters:**
```
/bedrock-budgeteer/production/cost/budget_refresh_period_days = "30"
```

### Metric Dimensions

**Budget Metrics:**
```python
{
  "Environment": "production",
  "PrincipalId": "user-id"  # optional
}
```

**System Metrics:**
```python
{
  "Environment": "production",
  "FunctionName": "lambda-function-name"  # optional
}
```

## Extension Points

### Adding Custom Lambda Functions

```python
# In CoreProcessingConstruct
def _create_custom_lambda(self, common_config: Dict[str, Any]) -> None:
    """Create custom Lambda function"""
    
    self.lambda_functions["custom_function"] = lambda_.Function(
        self,
        "CustomFunction",
        function_name=f"bedrock-budgeteer-custom-{self.environment_name}",
        code=lambda_.Code.from_inline(custom_function_code),
        handler="index.lambda_handler",
        **common_config
    )
```

### Adding Custom Metrics

```python
# In shared utilities
MetricsPublisher.publish_budget_metric(
    "CustomMetric",
    value,
    "Count", 
    {"Environment": "production", "Source": "custom"}
)
```

### Adding Custom Workflow Steps

```python
# In workflow definition
custom_step = self.create_lambda_invoke_task(
    "CustomStep",
    "custom_function",
    {"input": "data"},
    "$.custom_result"
)

# Chain with other steps
definition = start_step.next(custom_step).next(end_step)
```

This API reference provides comprehensive documentation for all public interfaces and extension points in the Bedrock Budgeteer system.
