# Bedrock Budgeteer Tagging Strategy

## Overview
Consistent resource tagging for cost allocation, operational management, and compliance tracking across all AWS resources in the Bedrock Budgeteer system.

## Required Tags (All Resources)

### Application Tags
- **App**: `bedrock-budgeteer`
- **Component**: Service component (e.g., `user-management`, `budget-monitor`, `notification-service`)
- **Version**: Application version (e.g., `v1.0.0`)

### Operational Tags  
- **Environment**: `dev`, `staging`, `prod`
- **Owner**: `FinOps` (team responsible)
- **Project**: `cost-management`

### Cost Allocation Tags
- **CostCenter**: `engineering-ops`
- **BillingProject**: `bedrock-budget-control`
- **Service**: AWS service type (e.g., `lambda`, `dynamodb`, `stepfunctions`)

### Compliance Tags
- **Compliance**: `soc2`, `gdpr` (applicable compliance frameworks)
- **DataClassification**: `internal`, `confidential` (data sensitivity)
- **BackupRequired**: `true`, `false`

## Tag Implementation in CDK

### Stack-Level Tags (Applied to All Resources)
```python
from aws_cdk import Tags

# In app.py - apply to entire application
Tags.of(app).add("App", "bedrock-budgeteer")
Tags.of(app).add("Owner", "FinOps")  
Tags.of(app).add("Project", "cost-management")
Tags.of(app).add("CostCenter", "engineering-ops")
Tags.of(app).add("BillingProject", "bedrock-budget-control")
```

### Environment-Specific Tags
```python
# Environment-specific tags in stack instantiation
Tags.of(stack).add("Environment", environment_name)
```

### Resource-Specific Tags
```python
# Component and service-specific tags
dynamodb_table = dynamodb.Table(
    self, "UserBudgetTable",
    # ... other props
)
Tags.of(dynamodb_table).add("Component", "user-management")
Tags.of(dynamodb_table).add("Service", "dynamodb")
Tags.of(dynamodb_table).add("DataClassification", "confidential")
Tags.of(dynamodb_table).add("BackupRequired", "true")
```

## Tag Governance

### Automated Validation
- Use CDK Aspects to enforce required tags
- Implement tag validation in CI/CD pipeline
- AWS Config rules for tag compliance monitoring

### Cost Reporting Views
- **By Environment**: `Environment` tag
- **By Component**: `Component` tag  
- **By Team**: `Owner` tag
- **By Project**: `BillingProject` tag

### Lifecycle Management
- Tag-based resource lifecycle policies
- Automated cleanup based on `Environment` and `Version` tags
- Backup policies driven by `BackupRequired` tag

## Implementation Priority
1. Apply stack-level tags immediately
2. Add environment-specific tags during stack configuration
3. Implement resource-specific tags during construct creation
4. Add validation Aspects for enforcement

## Compliance Mapping
- **SOC2**: All resources tagged with `Compliance: soc2`
- **GDPR**: Personal data resources tagged with `DataClassification: confidential`
- **Cost Control**: All resources tagged for cost center allocation
