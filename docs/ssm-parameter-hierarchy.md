# SSM Parameter Store Hierarchy

## Overview
Centralized configuration management using AWS Systems Manager Parameter Store with production values and secure string encryption for sensitive data.

**SIMPLIFIED**: This hierarchy has been significantly reduced to include only parameters that are actually used by the application. All unused parameters have been removed to reduce complexity and maintenance overhead.

## Parameter Hierarchy Structure (Only Used Parameters)

```
/bedrock-budgeteer/production/
├── cost/
│   └── budget_refresh_period_days
└── monitoring/
    └── log_retention_days

/bedrock-budgeteer/global/
├── thresholds_percent_warn
├── thresholds_percent_critical
├── default_user_budget_usd
└── grace_period_seconds
```

## Parameter Details

### 1. Cost Configuration (Environment-Specific)
**Path**: `/bedrock-budgeteer/production/cost/`

| Parameter | Type | Value | Description | Used By |
|-----------|------|-------|-------------|---------|
| `budget_refresh_period_days` | String | 30 | Budget refresh period in days | User setup & usage calculator Lambdas |

### 2. Monitoring Configuration (Environment-Specific)
**Path**: `/bedrock-budgeteer/production/monitoring/`

| Parameter | Type | Value | Description | Used By |
|-----------|------|-------|-------------|---------|
| `log_retention_days` | String | 7 | CloudWatch log group retention period in days | All CloudWatch log groups (Lambda functions, Step Functions, Bedrock logs) |

### 3. Global Configuration  
**Path**: `/bedrock-budgeteer/global/`

| Parameter | Type | Value | Description | Used By |
|-----------|------|-------|-------------|---------|
| `thresholds_percent_warn` | String | 70 | Budget warning threshold percentage | ConfigurationManager in Lambdas |
| `thresholds_percent_critical` | String | 90 | Budget critical threshold percentage | ConfigurationManager in Lambdas |
| `default_user_budget_usd` | String | 1 | Default budget limit for users in USD | User setup and usage calculator Lambdas |
| `grace_period_seconds` | String | 300 | Grace period in seconds before suspending users who exceed budget | Budget monitor and suspension workflows |

## Parameter Types

### Standard String Parameters
- **Usage**: All parameters are standard string parameters
- **Encryption**: None (no sensitive data in these parameters)
- **Cost**: $0.05 per 10,000 requests

## Access Patterns

### Lambda Function Access
```python
import boto3
import os

def get_parameter(parameter_name: str, decrypt: bool = False) -> str:
    """Get parameter value from SSM Parameter Store"""
    ssm = boto3.client('ssm')
    
    response = ssm.get_parameter(
        Name=parameter_name,
        WithDecryption=decrypt
    )
    
    return response['Parameter']['Value']

# Usage in Lambda function
budget_limit = get_parameter(
    '/bedrock-budgeteer/production/cost/budget_refresh_period_days'
)

# Global parameters
```

### CDK Reference Access
```python
# In CDK constructs
budget_limit = ssm.StringParameter.value_for_string_parameter(
    self, '/bedrock-budgeteer/production/cost/budget_refresh_period_days'
)

# Use in Lambda environment variables
lambda_function = lambda_.Function(
    self, "BudgetMonitor",
    environment={
        'BUDGET_LIMIT': budget_limit,
        'ENVIRONMENT': 'production'
    }
)
```

## IAM Permissions

### Read-Only Access (Lambda Functions)
```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "ssm:GetParameter",
                "ssm:GetParameters",
                "ssm:GetParametersByPath"
            ],
            "Resource": [
                "arn:aws:ssm:*:*:parameter/bedrock-budgeteer/*"
            ]
        }
    ]
}
```

## Management Examples

### Setting Parameters via CLI
```bash
# Set budget refresh period to 30 days (default)
aws ssm put-parameter \
  --name "/bedrock-budgeteer/production/cost/budget_refresh_period_days" \
  --value "30" \
  --type "String" \
  --overwrite

# Set to 7 days for weekly refresh
aws ssm put-parameter \
  --name "/bedrock-budgeteer/production/cost/budget_refresh_period_days" \
  --value "7" \
  --type "String" \
  --overwrite

# Warning at 60%, Critical at 85%
aws ssm put-parameter \
  --name "/bedrock-budgeteer/global/thresholds_percent_warn" \
  --value "60" \
  --type "String" \
  --overwrite

aws ssm put-parameter \
  --name "/bedrock-budgeteer/global/thresholds_percent_critical" \
  --value "85" \
  --type "String" \
  --overwrite


# Emergency stop (halts all automation)
aws ssm put-parameter \
  --name "/bedrock-budgeteer/global/emergency_stop_active" \
  --value "true" \
  --type "String" \
  --overwrite

# Exempt specific users from budget restrictions
aws ssm put-parameter \
  --name "/bedrock-budgeteer/global/user_whitelist" \
  --value '["admin@company.com", "service-account-1"]' \
  --type "String" \
  --overwrite
```

## Removed Parameters

The following parameter categories were removed as they were not used by any Lambda functions or constructs:

- **Application Config**: `name`, `version`, `log_level`, `region`
- **Security Config**: `encryption_enabled`, `session_timeout`, `max_budget_amount`, `api_rate_limit`  
- **Monitoring Config**: `error_threshold`, `latency_threshold`, `dashboard_refresh`, `log_retention_days`
- **Integration Config**: `bedrock_region`, `pricing_api_region`, `cloudtrail_enabled`, `notification_channels`
- **Most Cost Config**: `default_budget_limit`, `budget_alert_thresholds`, `cost_calculation_interval`, `suspension_threshold`, `grace_period_hours`
- **All Workflow Config**: All 8 workflow parameters were unused
- **Some Global Config**: `anomaly_detection_enabled`, `default_service_budget_usd`, `admin_emails`

This simplification reduces the parameter count from ~50 to 9 parameters, making the system much easier to manage and understand.