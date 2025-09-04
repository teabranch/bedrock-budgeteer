# Bedrock Budgeteer Deployment Guide

## Overview
This guide provides comprehensive instructions for deploying the Bedrock Budgeteer serverless system, configuring parameters, and managing the deployment lifecycle. The system is designed as a single-environment solution with all resources deployed to one AWS region.

## Table of Contents
1. [Prerequisites](#prerequisites)
2. [Environment Setup](#environment-setup)
3. [Encryption Configuration](#encryption-configuration)
4. [Parameter Configuration](#parameter-configuration)
5. [Deployment Process](#deployment-process)
6. [Post-Deployment Verification](#post-deployment-verification)
7. [Configuration Options](#configuration-options)
8. [Troubleshooting](#troubleshooting)
9. [Maintenance](#maintenance)

## Prerequisites

### Required Software
- **Python 3.11+** - Runtime for CDK and Lambda functions
- **Node.js 18+** - Required for AWS CDK CLI
- **AWS CDK CLI v2** - Install with `npm install -g aws-cdk@2`
- **AWS CLI v2** - For AWS credential configuration
- **Git** - For source code management

### AWS Requirements
- **AWS Account** with appropriate permissions
- **CDK Bootstrap** completed in target account/region
- **IAM Permissions** for deployment (see [IAM Requirements](#iam-requirements))

### Account Setup
```bash
# Install CDK CLI globally
npm install -g aws-cdk@2

# Verify CDK installation
cdk --version

# Bootstrap CDK (one-time per account/region)
cdk bootstrap aws://ACCOUNT-NUMBER/REGION
```

## Environment Setup

### 1. Clone Repository
```bash
git clone <repository-url>
cd bedrock-budgeteer
```

### 2. Python Environment Setup
```bash
cd app
python3 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -r requirements.txt
pip install -r requirements-dev.txt  # For development/testing
```

### 3. AWS Credentials Configuration
Configure AWS credentials using one of these methods:

#### Option A: AWS CLI Configuration
```bash
aws configure
# Enter Access Key ID, Secret Access Key, Region, Output Format
```

#### Option B: Environment Variables
```bash
export AWS_ACCESS_KEY_ID=your-access-key
export AWS_SECRET_ACCESS_KEY=your-secret-key
export AWS_DEFAULT_REGION=us-east-1
```

#### Option C: AWS Profile
```bash
aws configure --profile bedrock-budgeteer
export AWS_PROFILE=bedrock-budgeteer
```

## Encryption Configuration

### Default Encryption (Recommended for Most Users)
By default, Bedrock Budgeteer uses **AWS-managed encryption** for all services, providing:
- **No additional setup required**
- **No additional costs**
- **Automatic key management by AWS**
- **Basic encryption at rest**

Services use the following encryption:
- **DynamoDB**: AWS-managed encryption (SSE)
- **S3 Buckets**: S3-managed encryption (SSE-S3)
- **CloudTrail**: S3 bucket encryption settings
- **Lambda**: Default AWS encryption

### Custom KMS Key (Enhanced Security)
For enhanced security and compliance, you can optionally provide your own Customer-Managed KMS Key.

**Before deployment with a custom KMS key:**
1. Create a KMS key in your AWS account
2. Configure key policies to allow Bedrock Budgeteer roles access
3. Pass the KMS key ARN during deployment

**Benefits of Custom KMS Keys:**
- Full control over encryption keys
- Enhanced audit trail via CloudTrail
- Required for compliance frameworks (HIPAA, SOC 2, etc.)
- Cross-account access control

**Setup Instructions:**
See the comprehensive [KMS Setup Guide](kms-setup-guide.md) for detailed instructions on:
- Creating and configuring KMS keys
- Setting up IAM policies and permissions
- Deployment options with custom KMS keys
- Cost considerations and best practices

### Quick KMS Setup
```bash
# Create KMS key (replace account/region)
aws kms create-key --description "Bedrock Budgeteer Encryption"

# Create alias for easier management
aws kms create-alias \
  --alias-name alias/bedrock-budgeteer \
  --target-key-id YOUR_KEY_ID

# Deploy with custom KMS key
cdk deploy --context kmsKeyArn="arn:aws:kms:us-east-1:123456789012:key/YOUR_KEY_ID"
```

**Important:** If using a custom KMS key, ensure the key policy allows access to the Bedrock Budgeteer service roles. See the [KMS Setup Guide](kms-setup-guide.md) for complete policy examples.

## Parameter Configuration

### Required Environment Variables
Set these before deployment:

```bash
# Deployment Configuration
export AWS_ACCOUNT=123456789012          # Target AWS account ID
export AWS_REGION=us-east-1              # Target AWS region (default: us-east-1)

# Notification Configuration (Optional)
export OPS_EMAIL=ops@yourcompany.com     # Operations team email
export ALERT_EMAIL=alerts@yourcompany.com # Alert notifications email

# Advanced Notification Channels
export SLACK_WEBHOOK_URL=https://hooks.slack.com/your-webhook
export OPS_PHONE_NUMBER=+1234567890      # For SMS alerts
export EXTERNAL_WEBHOOK_URL=https://webhook.yourcompany.com
export WEBHOOK_AUTH_TOKEN=your-auth-token
```

### CDK Context Configuration
The `app/cdk.json` file contains the application configuration:

```json
{
  "app": "python app.py",
  "watch": {
    "include": ["**"],
    "exclude": ["README.md", "cdk*.json", "requirements*.txt", "source.bat", "**/__pycache__", "**/*.pyc"]
  },
  "context": {
    "bedrock-budgeteer:config": {
      "region": "us-east-1",
      "alert-email": "ops-alerts@company.com",
      "budget-limits": {
        "default-user-budget": 25,
        "max-user-budget": 50
      },
      "retention": {
        "logs": 180,
        "data": 2555
      }
    }
  }
}
```

### SSM Parameter Pre-Configuration (Optional)
You can pre-configure SSM parameters before deployment:

```bash
# Core budget configuration
aws ssm put-parameter \
  --name "/bedrock-budgeteer/global/default_user_budget_usd" \
  --value "25" \
  --type "String" \
  --description "Default user budget limit in USD"

# Threshold configuration
aws ssm put-parameter \
  --name "/bedrock-budgeteer/global/thresholds_percent_warn" \
  --value "70" \
  --type "String" \
  --description "Budget warning threshold percentage"

aws ssm put-parameter \
  --name "/bedrock-budgeteer/global/thresholds_percent_critical" \
  --value "90" \
  --type "String" \
  --description "Budget critical threshold percentage"

# Grace period configuration (suspension workflow timing)
aws ssm put-parameter \
  --name "/bedrock-budgeteer/global/grace_period_seconds" \
  --value "60" \
  --type "String" \
  --description "Grace period in seconds before suspending users (60 = 1 minute)"

# Security configuration
aws ssm put-parameter \
  --name "/bedrock-budgeteer/production/security/max_budget_amount" \
  --value "50" \
  --type "String" \
  --description "Maximum allowed budget amount in USD"
```

## Deployment Process

### 1. Validate Configuration
```bash
cd app

# Validate CDK synthesis
cdk synth

# Check for any synthesis errors
echo $?  # Should return 0 for success
```

### 2. Review Changes
```bash
# See what resources will be created/modified
cdk diff
```

### 3. Deploy Infrastructure
```bash
# Deploy with manual approval
cdk deploy --require-approval broadening

# Deploy with automatic approval (use carefully)
cdk deploy --require-approval never
```

### 4. Monitor Deployment
```bash
# Watch CloudFormation stack deployment in AWS Console
# Monitor deployment logs for any errors
# Verify all resources are created successfully
```

## Post-Deployment Verification

### 1. Verify Core Infrastructure
```bash
# Check DynamoDB tables
aws dynamodb list-tables --output table

# Verify Lambda functions
aws lambda list-functions --query 'Functions[?contains(FunctionName, `bedrock-budgeteer`)].FunctionName' --output table

# Check Step Functions state machines
aws stepfunctions list-state-machines --query 'stateMachines[?contains(name, `bedrock-budgeteer`)].name' --output table
```

### 2. Test Notifications
```bash
# Test SNS topic subscriptions
aws sns list-subscriptions --output table

# Manually trigger a test notification (if configured)
aws sns publish \
  --topic-arn arn:aws:sns:${AWS_REGION}:${AWS_ACCOUNT}:bedrock-budgeteer-operational-alerts \
  --message "Test deployment notification"
```

### 3. Verify Monitoring
```bash
# Check CloudWatch dashboards
aws cloudwatch list-dashboards --output table

# Verify alarms are created
aws cloudwatch describe-alarms --query 'MetricAlarms[?contains(AlarmName, `bedrock-budgeteer`)].AlarmName' --output table
```

### 4. Test Core Functionality
```bash
# Run unit tests
cd app
python -m pytest tests/unit/ -v

# Check circuit breaker status
aws ssm get-parameter --name "/bedrock-budgeteer/global/circuit_breaker_enabled"
```

## Configuration Options

### Standard Deployment
```bash
export AWS_ACCOUNT=123456789012
export AWS_REGION=us-east-1

# Deploy with standard settings
cdk deploy --require-approval broadening
```

**Features:**
- Full encryption enabled
- 180-day log retention
- Production-grade monitoring
- Multi-channel notifications
- Single-region serverless architecture

## Advanced Deployment Options

### Custom Parameter Overrides
```bash
# Deploy with custom budget limits
cdk deploy \
  --context default-user-budget=50 \
  --context max-user-budget=100
```

### Notification Channel Configuration
```bash
# Deploy with all notification channels
export SLACK_WEBHOOK_URL=https://hooks.slack.com/your-webhook
export OPS_PHONE_NUMBER=+1234567890

cdk deploy
```

## IAM Requirements

### Deployment Permissions
The deploying user/role needs these permissions:

```json
{
  "Version": "2012-10-17", 
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "cloudformation:*",
        "iam:*",
        "lambda:*",
        "dynamodb:*",
        "s3:*",
        "sns:*",
        "events:*",
        "logs:*",
        "ssm:*",
        "stepfunctions:*",
        "firehose:*",
        "cloudtrail:*",
        "cloudwatch:*",
        "kms:*"
      ],
      "Resource": "*"
    }
  ]
}
```

### Service Permissions
The system creates least-privilege roles for:
- Lambda execution roles
- Step Functions execution role  
- EventBridge service role
- Kinesis Firehose delivery role

## Troubleshooting

### Common Deployment Issues

#### CDK Bootstrap Required
```bash
Error: Need to perform AWS CDK bootstrap
Solution: cdk bootstrap aws://ACCOUNT/REGION
```

#### Insufficient Permissions
```bash
Error: AccessDenied
Solution: Verify IAM permissions and policy attachments
```

#### Parameter Store Conflicts
```bash
Error: Parameter already exists
Solution: Use --overwrite flag or delete existing parameters
```

#### Stack Dependency Issues
```bash
Error: Resource dependencies
Solution: Deploy stacks in correct order or use --exclusively
```

### Validation Commands
```bash
# Validate CDK app
cdk synth

# Validate CloudFormation template
aws cloudformation validate-template --template-body file://cdk.out/BedrockBudgeteer.template.json

# Test parameter access
aws ssm get-parameter --name "/bedrock-budgeteer/production/cost/default_budget_limit"
```

### Debug Mode
```bash
# Enable CDK debug output
cdk deploy --debug

# Enable Lambda debug logging
aws ssm put-parameter \
  --name "/bedrock-budgeteer/production/application/log_level" \
  --value "DEBUG" \
  --overwrite
```

## Maintenance

### Regular Updates
```bash
# Update CDK and dependencies
npm update -g aws-cdk
cd app && pip install -r requirements.txt --upgrade

# Re-deploy with updates
cdk deploy
```

### Parameter Management
```bash
# List all parameters
aws ssm describe-parameters \
  --parameter-filters "Key=Name,Option=BeginsWith,Values=/bedrock-budgeteer/"

# Update parameter
aws ssm put-parameter \
  --name "/bedrock-budgeteer/production/cost/default_budget_limit" \
  --value "50" \
  --overwrite
```

### Monitoring & Alerts
```bash
# Check system health
aws cloudwatch get-metric-statistics \
  --namespace "BedrockBudgeteer" \
  --metric-name "SystemHealth" \
  --start-time $(date -u -d '1 hour ago' +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 300 \
  --statistics Average
```

### Backup & Recovery
```bash
# Export DynamoDB tables
aws dynamodb create-backup \
  --table-name bedrock-budgeteer-user-budgets \
  --backup-name "user-budgets-$(date +%Y%m%d)"

# Export parameter configurations
aws ssm get-parameters-by-path \
  --path "/bedrock-budgeteer/production/" \
  --recursive > parameters-backup-$(date +%Y%m%d).json
```

## Security Considerations

### Secrets Management
- Use SSM SecureString for sensitive values
- Rotate secrets regularly
- Implement least-privilege access
- Monitor parameter access logs

### Network Security
- Deploy in private subnets where possible
- Use VPC endpoints for AWS services
- Implement WAF for public endpoints
- Monitor network traffic

### Data Protection
- Enable encryption at rest
- Use HTTPS for all communications
- Implement data retention policies
- Regular security audits

## Cost Optimization

### Serverless Cost Optimization
- Use PAY_PER_REQUEST billing for DynamoDB (scales to zero)
- Optimized Lambda memory allocation
- Lifecycle policies for S3 storage
- Comprehensive monitoring for cost tracking
- No persistent infrastructure costs

## Support

For deployment issues:
1. Check [troubleshooting section](#troubleshooting)
2. Review CloudFormation stack events
3. Check CloudWatch logs for Lambda functions
4. Validate IAM permissions
5. Consult AWS documentation for service-specific issues

For configuration questions:
- See [SSM Parameter Hierarchy](ssm-parameter-hierarchy.md)
- Check [Cost Optimization Guide](cost-optimization-guide.md)
