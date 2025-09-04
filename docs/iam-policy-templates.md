# IAM Policy Templates for Bedrock Budgeteer

## Overview
Reusable IAM policy templates following least-privilege principles for secure multi-service workflows.

## Core Policy Templates

### 1. Lambda Execution Policy Template
```python
# Basic Lambda execution with CloudWatch logs
lambda_policy = security.create_lambda_policy_template(
    function_name="user-manager",
    additional_permissions=[
        {
            "actions": ["dynamodb:GetItem", "dynamodb:PutItem"],
            "resources": ["arn:aws:dynamodb:*:*:table/user-budgets"]
        }
    ]
)
```

### 2. DynamoDB Access Policy Template
- **Actions**: GetItem, PutItem, UpdateItem, DeleteItem, Query, Scan
- **Resources**: Environment-scoped table ARNs and indexes
- **Scope**: Limited to application tables only

### 3. EventBridge Publishing Policy Template
- **Actions**: events:PutEvents
- **Resources**: Application-specific event buses
- **Scope**: No access to default event bus for cross-account security

### 4. KMS Access Policy Template
```python
# For DynamoDB encryption
kms_policy = security.create_kms_access_policy(
    key_arn="arn:aws:kms:region:account:key/key-id",
    actions=["kms:Encrypt", "kms:Decrypt", "kms:GenerateDataKey*"]
)
```

### 5. Service-Specific Policy Template
```python
# Generic template for any AWS service
custom_policy = security.create_policy_template(
    service_name="bedrock",
    actions=["bedrock:InvokeModel", "bedrock:GetFoundationModel"],
    resources=["*"]  # Bedrock requires wildcard
)
```

## Cross-Service Permission Patterns

### Lambda → DynamoDB
- **Pattern**: Function-specific policies with table-scoped permissions
- **Example**: User management function can only access user-budgets table
- **Implementation**: Attach DynamoDB access policy to Lambda execution role

### Lambda → EventBridge
- **Pattern**: Publish-only permissions to application event buses
- **Example**: Budget monitoring function publishes to budget-alerts bus
- **Implementation**: EventBridge publish policy attached to Lambda role

### Step Functions → Lambda
- **Pattern**: Invoke-only permissions on specific function ARNs
- **Example**: Workflow can invoke user-setup and budget-check functions
- **Implementation**: Lambda invoke permissions added to Step Functions role

### EventBridge → Lambda
- **Pattern**: Resource-based policies on Lambda functions
- **Example**: Budget alerts trigger suspension workflow
- **Implementation**: CDK automatically configures resource policies

## Environment-Specific Configurations

### Development Environment
- **Encryption**: Optional (cost optimization)
- **Scope**: Relaxed resource restrictions
- **Monitoring**: Basic CloudWatch permissions

### Staging Environment
- **Encryption**: Required (production-like)
- **Scope**: Production-equivalent restrictions
- **Monitoring**: Enhanced logging and metrics

### Production Environment
- **Encryption**: Required (compliance)
- **Scope**: Strictest least-privilege enforcement
- **Monitoring**: Full observability permissions

## Security Best Practices

### Resource Scoping
```python
# Good: Specific resource ARN
resources=["arn:aws:dynamodb:*:*:table/bedrock-budgeteer-prod-user-budgets"]

# Bad: Wildcard access
resources=["*"]
```

### Action Scoping
```python
# Good: Specific required actions
actions=["dynamodb:GetItem", "dynamodb:PutItem"]

# Bad: Administrative permissions
actions=["dynamodb:*"]
```

### Condition-Based Access
```python
# Example: Time-based access restrictions
conditions={
    "DateGreaterThan": {
        "aws:CurrentTime": "2024-01-01T00:00:00Z"
    }
}
```

### Cross-Account Protection
- No cross-account role assumptions
- Environment-specific account isolation
- Resource ARNs include account IDs

## Policy Validation Checklist

- [ ] Resource ARNs are environment-specific
- [ ] Actions follow minimum required principle
- [ ] No wildcard permissions unless AWS service requires it
- [ ] Cross-service permissions are explicitly scoped
- [ ] Sensitive data access is encrypted in transit/rest
- [ ] Policy names include environment identifier
- [ ] Regular access review procedures established

## Usage Examples

### Creating a Budget Monitor Function Policy
```python
budget_monitor_policy = security.create_lambda_policy_template(
    function_name="budget-monitor",
    additional_permissions=[
        {
            "actions": [
                "dynamodb:Query",
                "dynamodb:GetItem"
            ],
            "resources": [
                "arn:aws:dynamodb:*:*:table/bedrock-budgeteer-prod-user-budgets",
                "arn:aws:dynamodb:*:*:table/bedrock-budgeteer-prod-usage-tracking"
            ]
        },
        {
            "actions": ["events:PutEvents"],
            "resources": ["arn:aws:events:*:*:event-bus/budget-alerts"]
        }
    ]
)
```

### Attaching Policies to Roles
```python
# Attach custom policy to Lambda execution role
lambda_execution_role.add_managed_policy(budget_monitor_policy)

# Attach AWS managed policy for basic execution
lambda_execution_role.add_managed_policy(
    iam.ManagedPolicy.from_aws_managed_policy_name(
        "service-role/AWSLambdaBasicExecutionRole"
    )
)
```
