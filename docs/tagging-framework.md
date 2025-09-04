# Tagging Framework Implementation

## Overview
Automated tagging framework using CDK Aspects to ensure consistent, compliant, and cost-optimized resource tagging across all environments.

## Framework Components

### 1. TaggingAspect (Core Tags)
Applies required tags to all resources:
- **App**: bedrock-budgeteer
- **Owner**: FinOps
- **Project**: cost-management
- **CostCenter**: engineering-ops
- **BillingProject**: bedrock-budget-control
- **Environment**: dev/staging/prod
- **ManagedBy**: cdk

### 2. ComplianceTaggingAspect (Security & Compliance)
Applies compliance-specific tags based on resource type:

#### DynamoDB Tables
- **DataClassification**: confidential
- **BackupRequired**: true
- **Compliance**: soc2,gdpr

#### Lambda Functions
- **DataClassification**: internal
- **SecurityScan**: required
- **Compliance**: soc2

#### KMS Keys
- **DataClassification**: confidential
- **KeyRotation**: enabled
- **Compliance**: soc2,gdpr

### 3. CostOptimizationAspect (Cost Management)
Environment-specific cost optimization tags:

#### Development
- **AutoShutdown**: enabled
- **CostOptimization**: aggressive
- **ResourceTTL**: 7days

#### Staging
- **AutoShutdown**: scheduled
- **CostOptimization**: moderate
- **ResourceTTL**: 30days

#### Production
- **AutoShutdown**: disabled
- **CostOptimization**: conservative
- **ResourceTTL**: permanent

## Usage

### Automatic Application
Tags are automatically applied to all resources through CDK Aspects:

```python
# In app_stack.py - automatically applies to all resources
self.tagging_framework = TaggingFramework(
    self, "TaggingFramework",
    environment_name=environment_name
)
```

### Custom Resource Tags
For resource-specific tags, modify the `UnifiedTaggingAspect` class to include additional tags:

```python
# Add custom tags to the UnifiedTaggingAspect compliance_tags dictionary
self.compliance_tags = {
    "AWS::DynamoDB::Table": {
        "BackupRequired": "true",
        "TableType": "user-budgets",  # Custom tag
        "AccessPattern": "read-heavy"  # Custom tag
    }
}
```

## Tag Categories

### Required Tags (All Resources)
Applied automatically via TaggingAspect:
- Application identification
- Ownership and responsibility
- Cost allocation
- Environment classification

### Compliance Tags (By Resource Type)
Applied automatically via ComplianceTaggingAspect:
- Data classification levels
- Regulatory compliance requirements
- Security scanning requirements
- Audit trail configuration

### Cost Optimization Tags (Environment-Based)
Applied automatically via CostOptimizationAspect:
- Resource lifecycle management
- Auto-shutdown policies
- Cost optimization strategies

### Custom Tags (Resource-Specific)
Applied by modifying the UnifiedTaggingAspect for specific needs:
- Component classification
- Access patterns
- Performance characteristics
- Business context

## Cost Allocation Views

### By Environment
Use `Environment` tag to track costs across dev/staging/prod

### By Component
Use `Component` tag to track costs by system component

### By Team
Use `Owner` tag to allocate costs to responsible teams

### By Project
Use `BillingProject` tag for budget tracking and chargebacks

## Compliance Monitoring

### SOC2 Compliance
Filter resources by `Compliance` tag containing "soc2"

### GDPR Compliance
Filter resources by `Compliance` tag containing "gdpr"

### Data Classification
Use `DataClassification` tag to identify sensitive data resources

### Backup Requirements
Use `BackupRequired` tag to ensure backup policies are applied

## Operational Benefits

### 1. Automated Cost Tracking
- Consistent cost allocation across all resources
- Environment-based cost breakdown
- Component-level cost analysis

### 2. Compliance Validation
- Automated compliance tag application
- Easy identification of non-compliant resources
- Audit trail for regulatory requirements

### 3. Resource Lifecycle Management
- Environment-appropriate cleanup policies
- Cost optimization based on resource usage
- Automated shutdown for development resources

### 4. Operational Visibility
- Clear resource ownership
- Component dependency tracking
- Environment isolation validation

## Tag Validation

### AWS Config Rules
Create Config rules to validate required tags:
```json
{
  "ConfigRuleName": "required-tags-bedrock-budgeteer",
  "Source": {
    "Owner": "AWS",
    "SourceIdentifier": "REQUIRED_TAGS"
  },
  "InputParameters": {
    "requiredTagKeys": "App,Owner,Environment,Project"
  }
}
```

### CDK Validation
Tags are validated during CDK synthesis through Aspects

### CI/CD Integration
Include tag validation in deployment pipelines

## Best Practices

### 1. Consistent Naming
- Use kebab-case for tag keys
- Use lowercase for tag values
- Include environment in resource-specific tags

### 2. Automation First
- Rely on Aspects for consistent application
- Minimize manual tag application
- Use resource-specific tags sparingly

### 3. Regular Auditing
- Monitor untagged resources
- Validate tag compliance
- Update tag strategies based on usage

### 4. Cost Optimization
- Use tags for automated cleanup
- Implement cost allocation reporting
- Set up budget alerts based on tags
