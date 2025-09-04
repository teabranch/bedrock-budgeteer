# Comprehensive Deployment Guide - Bedrock Budgeteer

## Overview

This guide provides complete instructions for deploying the Bedrock Budgeteer system from scratch, including prerequisites, deployment procedures, configuration, and post-deployment verification.

## Prerequisites

### 1. Environment Setup

**Required Software:**
```bash
# Node.js 18+ for AWS CDK
node --version  # Should be 18.0.0 or higher

# Python 3.11+ for application code
python3 --version  # Should be 3.11.0 or higher

# AWS CLI v2
aws --version  # Should be 2.x

# AWS CDK CLI v2
npm install -g aws-cdk@2
cdk --version  # Should be 2.x
```

**AWS Account Requirements:**
- AWS Account with administrative access
- Sufficient service quotas for:
  - Lambda functions (20+ functions)
  - DynamoDB tables (4 tables)
  - CloudWatch log groups (20+ groups)
  - SNS topics (3 topics)
  - Step Functions state machines (2 machines)

### 2. AWS Credentials Configuration

**Option A: AWS CLI Profiles**
```bash
# Configure AWS credentials
aws configure --profile bedrock-budgeteer
# Enter Access Key ID, Secret Access Key, Region, and Output format
```

**Option B: Environment Variables**
```bash
export AWS_ACCESS_KEY_ID="your-access-key"
export AWS_SECRET_ACCESS_KEY="your-secret-key"
export AWS_DEFAULT_REGION="us-east-1"
```

**Option C: IAM Roles (Recommended for EC2/Cloud9)**
- Attach appropriate IAM role to EC2 instance
- No additional configuration required

### 3. Required AWS Permissions

The deployment user/role needs the following permissions:
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "cloudformation:*",
        "lambda:*",
        "dynamodb:*",
        "s3:*",
        "iam:*",
        "events:*",
        "sns:*",
        "stepfunctions:*",
        "logs:*",
        "ssm:*",
        "kms:*",
        "firehose:*",
        "cloudtrail:*",
        "bedrock:*",
        "pricing:*"
      ],
      "Resource": "*"
    }
  ]
}
```

## Step-by-Step Deployment

### Step 1: Clone and Setup Repository

```bash
# Clone the repository
git clone <repository-url>
cd bedrock-budgeteer

# Navigate to the app directory
cd app

# Create Python virtual environment
python3 -m venv .venv

# Activate virtual environment
# On macOS/Linux:
source .venv/bin/activate
# On Windows:
# .venv\Scripts\activate

# Install Python dependencies
pip install -r requirements.txt

# Verify CDK installation
cdk --version
```

### Step 2: CDK Bootstrap (One-time per Account/Region)

**Important**: The system requires specific bootstrap configuration to work properly.

```bash
# Bootstrap CDK with custom toolkit stack name and S3 configuration
cdk bootstrap \
  --toolkit-stack-name CDKToolkit-bedrock-budgeteer \
  --public-access-block-configuration false

# Verify bootstrap succeeded
aws cloudformation describe-stacks \
  --stack-name CDKToolkit-bedrock-budgeteer \
  --query 'Stacks[0].StackStatus'
```

**Why Custom Bootstrap?**
- Custom toolkit stack name prevents conflicts
- `public-access-block-configuration false` required for CloudTrail S3 bucket
- Ensures proper S3 bucket policies for CloudTrail

### Step 3: Pre-deployment Configuration (Optional)

**Set Environment Variables (Optional):**
```bash
# Set target region (default: us-east-1)
export CDK_DEFAULT_REGION="us-east-1"

# Set target account (auto-detected if not set)
export CDK_DEFAULT_ACCOUNT="123456789012"

# Set notification email (optional)
export OPS_EMAIL="admin@company.com"

# Set Slack webhook for notifications (optional)
export SLACK_WEBHOOK_URL="https://hooks.slack.com/services/..."

# Set PagerDuty integration key (optional)
export PAGERDUTY_INTEGRATION_KEY="your-integration-key"
```

### Step 4: Synthesize CloudFormation Template

```bash
# Generate CloudFormation template
cdk synth

# Review the generated template (optional)
# Template will be in cdk.out/BedrockBudgeteer.template.json
```

**What to Look For:**
- Verify all expected resources are present
- Check IAM roles have appropriate permissions
- Ensure S3 bucket policies are correctly configured
- Confirm DynamoDB tables have proper encryption

### Step 5: Deploy the System

```bash
# Deploy with automatic approval (recommended for CI/CD)
cdk deploy --require-approval never

# Alternative: Deploy with manual approval
cdk deploy
```

**Deployment Process:**
1. CloudFormation stack creation begins
2. IAM roles and policies created first
3. DynamoDB tables provisioned
4. S3 buckets and encryption configured
5. Lambda functions deployed
6. EventBridge rules activated
7. Step Functions state machines created
8. CloudWatch alarms and dashboards configured

**Expected Deployment Time:** 10-15 minutes

### Step 6: Verify Deployment

```bash
# Check stack status
aws cloudformation describe-stacks \
  --stack-name BedrockBudgeteer \
  --query 'Stacks[0].StackStatus'

# List created resources
aws cloudformation describe-stack-resources \
  --stack-name BedrockBudgeteer \
  --query 'StackResources[?ResourceStatus==`CREATE_COMPLETE`].[LogicalResourceId,ResourceType]' \
  --output table
```

## Post-Deployment Configuration

### Step 1: Configure SSM Parameters

The system will work with default values, but you can customize behavior:

```bash
# Set custom default budget (optional - default is $1)
aws ssm put-parameter \
  --name "/bedrock-budgeteer/global/default_user_budget_usd" \
  --value "25" \
  --type "String" \
  --overwrite

# Adjust warning threshold (optional - default is 70%)
aws ssm put-parameter \
  --name "/bedrock-budgeteer/global/thresholds_percent_warn" \
  --value "60" \
  --type "String" \
  --overwrite

# Adjust critical threshold (optional - default is 90%)
aws ssm put-parameter \
  --name "/bedrock-budgeteer/global/thresholds_percent_critical" \
  --value "85" \
  --type "String" \
  --overwrite

# Set grace period (optional - default is 300 seconds)
aws ssm put-parameter \
  --name "/bedrock-budgeteer/global/grace_period_seconds" \
  --value "600" \
  --type "String" \
  --overwrite

# Set budget refresh period (optional - default is 30 days)
aws ssm put-parameter \
  --name "/bedrock-budgeteer/production/cost/budget_refresh_period_days" \
  --value "7" \
  --type "String" \
  --overwrite
```

### Step 2: Configure Bedrock Invocation Logging

**Important**: You must manually configure Bedrock to send invocation logs to the created log group.

1. **Get the log group details:**
```bash
# Get the Bedrock logging role ARN
aws cloudformation describe-stacks \
  --stack-name BedrockBudgeteer \
  --query 'Stacks[0].Outputs[?OutputKey==`BedrockLoggingRoleArn`].OutputValue' \
  --output text

# Get the log group name
aws cloudformation describe-stacks \
  --stack-name BedrockBudgeteer \
  --query 'Stacks[0].Outputs[?OutputKey==`BedrockInvocationLogGroupName`].OutputValue' \
  --output text
```

2. **Configure Bedrock logging via AWS Console:**
   - Navigate to AWS Bedrock Console
   - Go to "Settings" → "Model Invocation Logging"
   - Enable logging with the following settings:
     - **CloudWatch Logs**: Enabled
     - **Log Group**: Use the log group name from step 1
     - **Role ARN**: Use the role ARN from step 1
     - **Log large text data**: Enabled
     - **Log image data**: Enabled (if using vision models)

3. **Alternative: Configure via CLI:**
```bash
# Get the values
ROLE_ARN=$(aws cloudformation describe-stacks \
  --stack-name BedrockBudgeteer \
  --query 'Stacks[0].Outputs[?OutputKey==`BedrockLoggingRoleArn`].OutputValue' \
  --output text)

LOG_GROUP=$(aws cloudformation describe-stacks \
  --stack-name BedrockBudgeteer \
  --query 'Stacks[0].Outputs[?OutputKey==`BedrockInvocationLogGroupName`].OutputValue' \
  --output text)

# Configure Bedrock logging
aws bedrock put-model-invocation-logging-configuration \
  --logging-config '{
    "cloudWatchConfig": {
      "logGroupName": "'$LOG_GROUP'",
      "roleArn": "'$ROLE_ARN'",
      "largeDataDeliveryS3Config": {
        "bucketName": "bedrock-budgeteer-production-cloudtrail"
      }
    },
    "textDataDeliveryEnabled": true,
    "imageDataDeliveryEnabled": true,
    "embeddingDataDeliveryEnabled": true
  }'
```

### Step 3: Set Up Notification Channels

**Email Notifications:**
```bash
# Email notifications are auto-configured if OPS_EMAIL environment variable was set
# To add additional email subscriptions:
aws sns subscribe \
  --topic-arn "arn:aws:sns:us-east-1:ACCOUNT:bedrock-budgeteer-production-operational-alerts" \
  --protocol email \
  --notification-endpoint "team@company.com"

# Confirm subscription via email link
```

**Slack Integration:**
```bash
# If SLACK_WEBHOOK_URL was set during deployment, Slack notifications are already configured
# To verify Slack integration, check Lambda function:
aws lambda get-function \
  --function-name "bedrock-budgeteer-production-slack-notifications"
```

### Step 4: Test the System

**Test Budget Monitoring:**
```bash
# Create a test user with low budget
aws dynamodb put-item \
  --table-name bedrock-budgeteer-production-user-budgets \
  --item '{
    "principal_id": {"S": "test-user@company.com"},
    "budget_limit_usd": {"N": "0.01"},
    "spent_usd": {"N": "0.02"},
    "status": {"S": "active"},
    "account_type": {"S": "bedrock_api_key"},
    "budget_period_start": {"S": "'$(date -u +"%Y-%m-%dT%H:%M:%SZ")'"},
    "created_at": {"S": "'$(date -u +"%Y-%m-%dT%H:%M:%SZ")'"}
  }'

# Trigger budget monitor manually
aws lambda invoke \
  --function-name bedrock-budgeteer-budget-monitor-production \
  --payload '{}' \
  /tmp/response.json

# Check response
cat /tmp/response.json
```

**Test User Creation:**
```bash
# Simulate API key creation event
aws events put-events \
  --entries '[{
    "Source": "aws.iam",
    "DetailType": "AWS API Call via CloudTrail",
    "Detail": "{\"eventName\":\"CreateUser\",\"responseElements\":{\"user\":{\"userName\":\"BedrockAPIKey-TestUser\"}}}"
  }]'

# Check if user was created in DynamoDB
aws dynamodb scan \
  --table-name bedrock-budgeteer-production-user-budgets \
  --filter-expression "contains(principal_id, :user)" \
  --expression-attribute-values '{":user":{"S":"BedrockAPIKey-TestUser"}}'
```

## Monitoring and Verification

### Step 1: Check CloudWatch Dashboards

1. Navigate to CloudWatch Console → Dashboards
2. Look for these dashboards:
   - `bedrock-budgeteer-production-system`
   - `bedrock-budgeteer-production-ingestion-pipeline`
   - `bedrock-budgeteer-production-workflow-orchestration`
   - `bedrock-budgeteer-production-business-metrics`

### Step 2: Verify Lambda Functions

```bash
# List all deployed Lambda functions
aws lambda list-functions \
  --query 'Functions[?starts_with(FunctionName, `bedrock-budgeteer`)].FunctionName' \
  --output table

# Check function logs
aws logs describe-log-groups \
  --log-group-name-prefix "/aws/lambda/bedrock-budgeteer" \
  --query 'logGroups[].logGroupName'
```

### Step 3: Verify DynamoDB Tables

```bash
# List DynamoDB tables
aws dynamodb list-tables \
  --query 'TableNames[?starts_with(@, `bedrock-budgeteer`)]'

# Check table status
aws dynamodb describe-table \
  --table-name bedrock-budgeteer-production-user-budgets \
  --query 'Table.TableStatus'
```

### Step 4: Verify Step Functions

```bash
# List state machines
aws stepfunctions list-state-machines \
  --query 'stateMachines[?starts_with(name, `bedrock-budgeteer`)].name'

# Check state machine status
aws stepfunctions describe-state-machine \
  --state-machine-arn "arn:aws:states:us-east-1:ACCOUNT:stateMachine:bedrock-budgeteer-suspension-production"
```

## Troubleshooting Common Issues

### Issue 1: CDK Bootstrap Fails

**Error**: `AccessDenied: User is not authorized to perform: sts:AssumeRole`

**Solution**:
```bash
# Check AWS credentials
aws sts get-caller-identity

# Ensure user has sufficient permissions
# Re-run bootstrap with correct profile
aws configure list
cdk bootstrap --profile your-profile
```

### Issue 2: S3 Bucket Policy Errors

**Error**: `PUT Bucket Public Access Block failed`

**Solution**:
```bash
# Use custom bootstrap command with public access block disabled
cdk bootstrap \
  --toolkit-stack-name CDKToolkit-bedrock-budgeteer \
  --public-access-block-configuration false
```

### Issue 3: Lambda Function Timeouts

**Error**: Lambda functions timing out during deployment

**Solution**:
```bash
# Check CloudWatch logs for specific errors
aws logs filter-log-events \
  --log-group-name "/aws/lambda/bedrock-budgeteer-user-setup-production" \
  --start-time 1640995200000

# Increase memory and timeout if needed
```

### Issue 4: DynamoDB Provisioning Errors

**Error**: `LimitExceededException: Account limit exceeded`

**Solution**:
```bash
# Check service quotas
aws service-quotas get-service-quota \
  --service-code dynamodb \
  --quota-code L-F98FE922

# Request quota increase if needed
```

### Issue 5: EventBridge Rules Not Triggering

**Problem**: Events not reaching Lambda functions

**Debug Steps**:
```bash
# Check EventBridge rule configuration
aws events describe-rule \
  --name bedrock-budgeteer-user-setup-production

# Test event pattern
aws events test-event-pattern \
  --event-pattern '{"source":["aws.iam"],"detail-type":["AWS API Call via CloudTrail"]}' \
  --event '{"source":"aws.iam","detail-type":"AWS API Call via CloudTrail"}'

# Check Lambda function permissions
aws lambda get-policy \
  --function-name bedrock-budgeteer-user-setup-production
```

## Rollback Procedures

### Option 1: Stack Rollback

```bash
# Rollback to previous version (if deployment failed)
aws cloudformation cancel-update-stack \
  --stack-name BedrockBudgeteer

# Wait for rollback to complete
aws cloudformation wait stack-update-complete \
  --stack-name BedrockBudgeteer
```

### Option 2: Complete Stack Deletion

```bash
# Delete the entire stack
cdk destroy

# Confirm deletion
aws cloudformation describe-stacks \
  --stack-name BedrockBudgeteer
```

**Note**: DynamoDB tables and S3 buckets have `RemovalPolicy.DESTROY` configured to allow proper cleanup.

## Production Deployment Checklist

- [ ] AWS credentials configured with sufficient permissions
- [ ] CDK bootstrap completed with custom configuration
- [ ] Environment variables set for notifications
- [ ] CloudFormation stack deployed successfully
- [ ] All Lambda functions operational
- [ ] DynamoDB tables created and accessible
- [ ] EventBridge rules configured and active
- [ ] CloudWatch dashboards and alarms functional
- [ ] Bedrock invocation logging configured
- [ ] SNS topics and subscriptions set up
- [ ] Test user creation and budget monitoring
- [ ] Production notification channels configured
- [ ] Documentation updated with environment-specific details

## Next Steps

After successful deployment:

1. **Configure Monitoring**: Set up production alerting thresholds
2. **User Training**: Train team on system operation and monitoring
3. **Backup Strategy**: Implement DynamoDB backup procedures
4. **Security Review**: Conduct security assessment of deployed resources
5. **Cost Optimization**: Review and optimize resource configurations
6. **Documentation**: Update runbooks with environment-specific details

## Support and Maintenance

**Regular Maintenance Tasks:**
- Monitor CloudWatch logs for errors
- Review DynamoDB metrics and adjust capacity as needed
- Update Lambda function code via CDK deployments
- Rotate IAM access keys and update secrets
- Review and update SSM parameters as requirements change

**Emergency Contacts:**
- System Administrator: [Contact Information]
- AWS Support: [Support Plan Details]
- Development Team: [Team Contact Information]
