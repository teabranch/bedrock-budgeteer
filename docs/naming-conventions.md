# Naming Conventions for Bedrock Budgeteer

## Overview
Consistent naming patterns for all AWS resources, ensuring clarity, organization, and automated management across environments.

## General Naming Pattern
```
{application}-{environment}-{component}-{resource-type}
```

**Example**: `bedrock-budgeteer-prod-user-management-lambda`

## Resource-Specific Naming Conventions

### 1. DynamoDB Tables
**Pattern**: `bedrock-budgeteer-{env}-{table-purpose}`

| Resource | Naming Example |
|----------|----------------|
| User budgets | `bedrock-budgeteer-prod-user-budgets` |
| Usage tracking | `bedrock-budgeteer-prod-usage-tracking` |
| Budget alerts | `bedrock-budgeteer-prod-budget-alerts` |

### 2. Lambda Functions
**Pattern**: `bedrock-budgeteer-{env}-{function-purpose}`

| Resource | Naming Example |
|----------|----------------|
| User setup | `bedrock-budgeteer-prod-user-setup` |
| Budget monitor | `bedrock-budgeteer-prod-budget-monitor` |
| Usage calculator | `bedrock-budgeteer-prod-usage-calculator` |
| Alert handler | `bedrock-budgeteer-prod-alert-handler` |

### 3. IAM Roles
**Pattern**: `bedrock-budgeteer-{env}-{service}-{purpose}`

| Resource | Naming Example |
|----------|----------------|
| Lambda execution | `bedrock-budgeteer-prod-lambda-execution` |
| Step Functions | `bedrock-budgeteer-prod-step-functions` |
| EventBridge | `bedrock-budgeteer-prod-eventbridge` |

### 4. IAM Policies
**Pattern**: `bedrock-budgeteer-{env}-{service}-{access-type}`

| Resource | Naming Example |
|----------|----------------|
| DynamoDB access | `bedrock-budgeteer-prod-dynamodb-access` |
| EventBridge publish | `bedrock-budgeteer-prod-eventbridge-publish` |
| S3 read-only | `bedrock-budgeteer-prod-s3-readonly` |

### 5. Step Functions
**Pattern**: `bedrock-budgeteer-{env}-{workflow-name}`

| Resource | Naming Example |
|----------|----------------|
| User suspension | `bedrock-budgeteer-prod-user-suspension` |
| Budget restoration | `bedrock-budgeteer-prod-budget-restoration` |
| Cost calculation | `bedrock-budgeteer-prod-cost-calculation` |

### 6. EventBridge Resources
**Pattern**: `bedrock-budgeteer-{env}-{purpose}`

| Resource | Naming Example |
|----------|----------------|
| Custom event bus | `bedrock-budgeteer-prod-budget-events` |
| Budget alert rule | `bedrock-budgeteer-prod-budget-alert-rule` |
| Usage tracking rule | `bedrock-budgeteer-prod-usage-tracking-rule` |

### 7. SNS Topics
**Pattern**: `bedrock-budgeteer-{env}-{notification-type}`

| Resource | Naming Example |
|----------|----------------|
| Operational alerts | `bedrock-budgeteer-prod-operational-alerts` |
| Budget alerts | `bedrock-budgeteer-prod-budget-alerts` |
| High severity | `bedrock-budgeteer-prod-high-severity` |

### 8. CloudWatch Resources
**Pattern**: `bedrock-budgeteer-{env}-{resource-type}`

| Resource | Naming Example |
|----------|----------------|
| Dashboard | `bedrock-budgeteer-prod-system` |
| Log group | `/aws/lambda/bedrock-budgeteer-prod-user-setup` |
| Alarm | `bedrock-budgeteer-prod-budget-monitor-errors` |

### 9. S3 Buckets
**Pattern**: `bedrock-budgeteer-{env}-{purpose}-{random-suffix}`

| Resource | Naming Example |
|----------|----------------|
| Usage data archive | `bedrock-budgeteer-prod-usage-archive-abc123` |
| CloudTrail logs | `bedrock-budgeteer-prod-cloudtrail-def456` |
| Backup storage | `bedrock-budgeteer-prod-backups-ghi789` |

### 10. KMS Keys
**Pattern**: `bedrock-budgeteer-{env}-{purpose}-key`

| Resource | Naming Example |
|----------|----------------|
| DynamoDB encryption | `bedrock-budgeteer-prod-dynamodb-key` |
| S3 encryption | `bedrock-budgeteer-prod-s3-key` |
| Parameter encryption | `bedrock-budgeteer-prod-ssm-key` |

### 11. SSM Parameters
**Pattern**: `/bedrock-budgeteer/{env}/{category}/{parameter-name}`

| Resource | Naming Example |
|----------|----------------|
| Budget limit | `/bedrock-budgeteer/prod/cost/default_budget_limit` |
| Log level | `/bedrock-budgeteer/prod/application/log_level` |
| API endpoint | `/bedrock-budgeteer/prod/integrations/bedrock_endpoint` |

## Environment Abbreviations
| Environment | Abbreviation | Usage |
|-------------|--------------|-------|
| Development | `dev` | Development and testing |
| Staging | `staging` | Pre-production validation |
| Production | `prod` | Live production system |

## Component Categories
| Component | Purpose | Examples |
|-----------|---------|----------|
| `user-management` | User operations | Setup, suspension, restoration |
| `budget-monitoring` | Budget tracking | Cost calculation, threshold checks |
| `usage-tracking` | Service usage | Event collection, aggregation |
| `notification-service` | Alerts and notifications | Email, SNS, webhooks |
| `data-storage` | Persistent storage | DynamoDB, S3, backups |
| `security` | Security controls | IAM, KMS, access management |
| `monitoring` | Observability | CloudWatch, dashboards, alarms |

## Tagging Integration
All resources follow naming conventions AND include standardized tags:

```python
# Example resource with naming and tagging
dynamodb.Table(
    self, "UserBudgetTable",
    table_name="bedrock-budgeteer-prod-user-budgets",
    tags={
        "App": "bedrock-budgeteer",
        "Environment": "prod",
        "Component": "data-storage",
        "Service": "dynamodb",
        "Purpose": "user-budget-tracking"
    }
)
```

## Naming Validation Rules

### 1. Length Constraints
- DynamoDB tables: 3-255 characters
- Lambda functions: 1-64 characters  
- IAM roles: 1-64 characters
- S3 buckets: 3-63 characters (globally unique)

### 2. Character Rules
- Use lowercase letters, numbers, hyphens
- No underscores in resource names (use in SSM parameters only)
- No spaces or special characters
- Start and end with alphanumeric characters

### 3. Uniqueness Requirements
- S3 buckets: Globally unique (append random suffix)
- CloudFormation logical IDs: Unique within stack
- IAM resources: Unique within account
- DynamoDB tables: Unique within account/region

## Implementation in CDK

### Consistent Naming Helper
```python
class NamingHelper:
    def __init__(self, app_name: str, environment: str):
        self.app_name = app_name
        self.environment = environment
    
    def resource_name(self, component: str, resource_type: str) -> str:
        """Generate consistent resource name"""
        return f"{self.app_name}-{self.environment}-{component}-{resource_type}"
    
    def table_name(self, purpose: str) -> str:
        """Generate DynamoDB table name"""
        return f"{self.app_name}-{self.environment}-{purpose}"
    
    def function_name(self, purpose: str) -> str:
        """Generate Lambda function name"""
        return f"{self.app_name}-{self.environment}-{purpose}"
    
    def parameter_path(self, category: str, key: str) -> str:
        """Generate SSM parameter path"""
        return f"/{self.app_name}/{self.environment}/{category}/{key}"
```

### Usage in Constructs
```python
# In construct initialization
naming = NamingHelper("bedrock-budgeteer", environment_name)

# DynamoDB table
table = dynamodb.Table(
    self, "UserBudgetTable",
    table_name=naming.table_name("user-budgets"),
    # ... other properties
)

# Lambda function
function = lambda_.Function(
    self, "BudgetMonitor",
    function_name=naming.function_name("budget-monitor"),
    # ... other properties
)
```

## Automation and Validation

### Pre-commit Hooks
```bash
#!/bin/bash
# Check naming convention compliance
grep -r "bedrock-budgeteer-[^-]*-[^-]*" app/ || {
    echo "❌ Resource names must follow naming conventions"
    exit 1
}
```

### CDK Validation
```python
@jsii.implements(IAspect)
class NamingValidationAspect:
    def visit(self, node: IConstruct) -> None:
        """Validate resource naming conventions"""
        if isinstance(node, CfnResource):
            # Check resource naming patterns
            pass
```

### CI/CD Validation
```yaml
- name: Validate naming conventions
  run: |
    python scripts/validate_naming.py app/
```

## Best Practices

### 1. Consistency
- Always use the same pattern for similar resources
- Maintain consistent abbreviations and terminology
- Apply naming rules uniformly across environments

### 2. Clarity
- Use descriptive names that explain resource purpose
- Avoid cryptic abbreviations
- Include environment context for easy identification

### 3. Automation
- Use helper functions for name generation
- Implement validation in CI/CD pipelines
- Document exceptions and their justifications

### 4. Evolution
- Version naming convention changes
- Provide migration paths for existing resources
- Communicate changes to all team members

## Common Pitfalls to Avoid

### 1. Inconsistent Patterns
❌ **Bad**: Mixed patterns across resources
```
bedrock-budgeteer-prod-user-budgets
bedrock_budgeteer_prod_usage_tracking
BedrockBudgeteerProdBudgetAlerts
```

✅ **Good**: Consistent pattern
```
bedrock-budgeteer-prod-user-budgets
bedrock-budgeteer-prod-usage-tracking
bedrock-budgeteer-prod-budget-alerts
```

### 2. Environment Confusion
❌ **Bad**: Unclear environment designation
```
bedrock-budgeteer-production-user-budgets
bedrock-budgeteer-dev-user-budgets
bedrock-budgeteer-test-user-budgets
```

✅ **Good**: Clear environment abbreviations
```
bedrock-budgeteer-prod-user-budgets
bedrock-budgeteer-dev-user-budgets
bedrock-budgeteer-staging-user-budgets
```

### 3. Resource Type Ambiguity
❌ **Bad**: Unclear resource purpose
```
bedrock-budgeteer-prod-data
bedrock-budgeteer-prod-handler
bedrock-budgeteer-prod-processor
```

✅ **Good**: Clear resource purpose
```
bedrock-budgeteer-prod-user-budgets
bedrock-budgeteer-prod-alert-handler
bedrock-budgeteer-prod-usage-processor
```
