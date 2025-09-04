# Bedrock Budgeteer

A comprehensive serverless budget monitoring and control system for AWS Bedrock API usage. Bedrock Budgeteer provides real-time cost tracking, automated threshold monitoring, and progressive access control to prevent budget overruns for AWS Bedrock AI services.

## 🎯 What It Does

Bedrock Budgeteer is an enterprise-grade solution that automatically monitors and controls AWS Bedrock API usage costs in real-time. It prevents budget overruns by:

- **Real-time cost tracking**: Monitors every Bedrock API call and calculates token-based costs using the AWS Pricing API
- **Automated budget enforcement**: Sets spending limits per user/API key with progressive controls (warnings → grace period → suspension)
- **Smart notifications**: Multi-channel alerts via email, Slack, and SMS
- **Operational safety**: Built-in audit trails and emergency controls
- **Zero-touch operation**: Fully serverless with automatic user setup and budget initialization

### Key Features

✅ **Real-time Budget Monitoring**
- Tracks token usage and costs for all Bedrock models
- Supports multiple threshold levels (warning, critical, exceeded)
- Automatic price updates from AWS Pricing API

✅ **Progressive Access Control**
- Grace period warnings before suspension
- Graduated response system (alert → warn → suspend)
- Automatic restoration when budgets refresh

✅ **Enterprise-Ready**
- Multi-channel notifications (Email, Slack, SMS)
- Comprehensive audit trails and compliance logging
- IAM policy-based access control

✅ **Serverless & Cost-Optimized**
- Pay-per-use architecture with no persistent infrastructure costs
- Auto-scaling DynamoDB and Lambda functions
- S3 lifecycle policies for log retention

✅ **Security & Compliance**
- Encryption at rest and in transit
- Least-privilege IAM roles
- Optional customer-managed KMS keys
- Complete audit trail

## 📋 Prerequisites

Before installation, ensure you have:

### Required Software
- **Python 3.11+** - Application runtime
- **Node.js 18+** - Required for AWS CDK CLI
- **AWS CDK CLI v2** - Infrastructure deployment tool
- **AWS CLI v2** - AWS credential management
- **Git** - Source code management

### AWS Requirements
- **AWS Account** with administrative access
- **CDK Bootstrap** completed in target account/region
- **Sufficient service quotas** for:
  - Lambda functions (20+ functions)
  - DynamoDB tables (4 tables)
  - CloudWatch log groups (20+ groups)
  - SNS topics (3 topics)
  - Step Functions state machines (2 machines)

### Install Required Tools

```bash
# Install Node.js and CDK CLI
npm install -g aws-cdk@2

# Verify installations
node --version    # Should be 18.0.0+
cdk --version     # Should be 2.x
python3 --version # Should be 3.11.0+
aws --version     # Should be 2.x
```

## 🚀 Installation

### Step 1: Clone Repository

```bash
git clone <repository-url>
cd bedrock-budgeteer
```

### Step 2: Set Up Python Environment

```bash
cd app
python3 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### Step 3: Configure AWS Credentials

Choose one of these methods:

**Option A: AWS CLI Configuration**
```bash
aws configure
# Enter your Access Key ID, Secret Access Key, Region, and Output Format
```

**Option B: Environment Variables**
```bash
export AWS_ACCESS_KEY_ID=your-access-key
export AWS_SECRET_ACCESS_KEY=your-secret-key
export AWS_DEFAULT_REGION=us-east-1
```

**Option C: AWS Profile**
```bash
aws configure --profile bedrock-budgeteer
export AWS_PROFILE=bedrock-budgeteer
```

### Step 4: Bootstrap CDK (One-time setup)

```bash
# Bootstrap CDK in your account/region
cdk bootstrap aws://YOUR-ACCOUNT-ID/YOUR-REGION

# Example:
cdk bootstrap aws://123456789012/us-east-1
```

### Step 5: Configure Environment Variables (Optional)

```bash
# Set notification email (recommended)
export OPS_EMAIL=ops@yourcompany.com
export ALERT_EMAIL=alerts@yourcompany.com

# Optional: Advanced notification channels
export SLACK_WEBHOOK_URL=https://hooks.slack.com/your-webhook
export OPS_PHONE_NUMBER=+1234567890
```

### Step 6: Deploy the System

```bash
# Preview what will be deployed
cdk diff

# Deploy with confirmation prompts
cdk deploy

# Or deploy without prompts (use carefully)
cdk deploy --require-approval never
```

**Expected deployment time:** 10-15 minutes

### Step 7: Verify Deployment

```bash
# Check stack status
aws cloudformation describe-stacks \
  --stack-name BedrockBudgeteer \
  --query 'Stacks[0].StackStatus'

# List created Lambda functions
aws lambda list-functions \
  --query 'Functions[?contains(FunctionName, `bedrock-budgeteer`)].FunctionName' \
  --output table

# Verify DynamoDB tables
aws dynamodb list-tables --output table
```

## 📖 How It Works

1. **Event Capture**: CloudTrail captures all Bedrock API calls in real-time
2. **Usage Processing**: Kinesis Firehose streams logs to Usage Calculator Lambda
3. **Cost Calculation**: Lambda calculates token costs using AWS Pricing API
4. **Budget Monitoring**: Budget Monitor checks thresholds every 5 minutes
5. **Progressive Control**: System applies warnings, grace periods, then suspension
6. **Automatic Restoration**: Users are restored when budgets refresh

### Architecture Overview

```
User → Bedrock API → CloudTrail → EventBridge → Lambda Functions
                                     ↓
DynamoDB ← Cost Calculation ← Kinesis Firehose ← CloudWatch Logs
   ↓
Budget Monitor → Step Functions → IAM Policies → Notifications
```

## ⚙️ Configuration

### Default Settings

The system comes with sensible defaults:
- **Default budget**: $1 per user
- **Warning threshold**: 70% of budget
- **Critical threshold**: 90% of budget
- **Grace period**: 5 minutes before suspension
- **Budget refresh**: Every 30 days

### Customizing Parameters

You can customize behavior using AWS Systems Manager Parameter Store:

```bash
# Change default budget to $25
aws ssm put-parameter \
  --name "/bedrock-budgeteer/global/default_user_budget_usd" \
  --value "25" \
  --type "String" \
  --overwrite

# Adjust warning threshold to 60%
aws ssm put-parameter \
  --name "/bedrock-budgeteer/global/thresholds_percent_warn" \
  --value "60" \
  --type "String" \
  --overwrite

# Set critical threshold to 85%
aws ssm put-parameter \
  --name "/bedrock-budgeteer/global/thresholds_percent_critical" \
  --value "85" \
  --type "String" \
  --overwrite

# Change grace period to 1 minute (60 seconds)
aws ssm put-parameter \
  --name "/bedrock-budgeteer/global/grace_period_seconds" \
  --value "60" \
  --type "String" \
  --overwrite

# Change budget refresh to weekly (7 days)
aws ssm put-parameter \
  --name "/bedrock-budgeteer/production/cost/budget_refresh_period_days" \
  --value "7" \
  --type "String" \
  --overwrite
```

### Available Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `default_user_budget_usd` | 1 | Default budget limit in USD |
| `thresholds_percent_warn` | 70 | Warning threshold percentage |
| `thresholds_percent_critical` | 90 | Critical threshold percentage |
| `grace_period_seconds` | 300 | Grace period before suspension |
| `budget_refresh_period_days` | 30 | Days between budget resets |


## 📊 Usage

### Monitoring

Access the CloudWatch dashboard to monitor:
- Real-time budget usage by user
- System health and performance metrics
- Alert history and trends
- Cost breakdown by model

### Viewing User Budgets

```bash
# List all user budgets
aws dynamodb scan \
  --table-name bedrock-budgeteer-user-budgets \
  --query 'Items[*].[principal_id.S, spent_usd.N, budget_limit_usd.N, status.S]' \
  --output table
```

### Manual Budget Management

```bash
# Check specific user budget
aws dynamodb get-item \
  --table-name bedrock-budgeteer-user-budgets \
  --key '{"principal_id": {"S": "BedrockAPIKey-example"}}' \
  --query 'Item.[principal_id.S, spent_usd.N, budget_limit_usd.N]' \
  --output table

# Reset user budget (emergency)
aws dynamodb update-item \
  --table-name bedrock-budgeteer-user-budgets \
  --key '{"principal_id": {"S": "BedrockAPIKey-example"}}' \
  --update-expression "SET spent_usd = :zero, #status = :active" \
  --expression-attribute-names '{"#status": "status"}' \
  --expression-attribute-values '{":zero": {"N": "0"}, ":active": {"S": "active"}}'
```

### Testing the System

```bash
# Run unit tests
cd app
python -m pytest tests/unit/ -v

# Test notifications
aws sns publish \
  --topic-arn arn:aws:sns:${AWS_REGION}:${AWS_ACCOUNT}:bedrock-budgeteer-operational-alerts \
  --message "Test notification from Bedrock Budgeteer"
```

## 🗑️ Deleting the Stack

### Option 1: CDK Destroy (Recommended)

```bash
# Delete the entire stack and all resources
cdk destroy

# Confirm when prompted
# This will delete:
# - All Lambda functions
# - DynamoDB tables (and their data)
# - S3 buckets (and their contents)
# - CloudWatch logs
# - IAM roles and policies
# - All other AWS resources
```

### Option 2: Manual Cleanup (If CDK destroy fails)

```bash
# Delete CloudFormation stack manually
aws cloudformation delete-stack --stack-name BedrockBudgeteer

# If S3 buckets have retention, delete them manually
aws s3 rm s3://bedrock-budgeteer-logs-bucket --recursive
aws s3 rb s3://bedrock-budgeteer-logs-bucket

# Delete any remaining SSM parameters
aws ssm delete-parameters \
  --names $(aws ssm get-parameters-by-path \
    --path "/bedrock-budgeteer/" \
    --recursive \
    --query 'Parameters[].Name' \
    --output text)
```

### Cost Implications

- **DynamoDB tables**: Configured with `DESTROY` removal policy - will be deleted
- **S3 buckets**: Configured with `auto_delete_objects` - contents will be deleted
- **CloudWatch logs**: Will be deleted with their retention policies
- **No persistent costs** after deletion

## 🔧 Troubleshooting

### Common Issues

**CDK Bootstrap Required**
```bash
Error: Need to perform AWS CDK bootstrap
Solution: cdk bootstrap aws://ACCOUNT/REGION
```

**Insufficient Permissions**
```bash
Error: AccessDenied
Solution: Verify IAM permissions include CloudFormation, Lambda, DynamoDB, S3, IAM, etc.
```

**Parameter Store Conflicts**
```bash
Error: Parameter already exists
Solution: Use --overwrite flag: aws ssm put-parameter --overwrite
```

### Debug Mode

```bash
# Enable detailed CDK output
cdk deploy --debug

# Enable Lambda debug logging
aws ssm put-parameter \
  --name "/bedrock-budgeteer/production/application/log_level" \
  --value "DEBUG" \
  --overwrite
```

### Support Resources

- 📚 **Documentation**: See the `/docs` folder for detailed guides
- 🏗️ **Architecture**: Review `docs/system-architecture.md`
- ⚙️ **Deployment**: See `docs/deployment-guide.md`
- 🔧 **Parameters**: Check `docs/ssm-parameter-hierarchy.md`

## 🛡️ Security Considerations

### Data Privacy
- Only necessary user identifiers are stored (no sensitive business data)
- All data encrypted at rest and in transit
- Minimal data collection approach

### Network Security
- All communications use HTTPS/TLS
- IAM roles follow least-privilege principle
- Optional VPC deployment for enhanced isolation

### Encryption Options

**Default (AWS-Managed)**
- No additional setup required
- AWS-managed encryption for all services
- Suitable for most use cases

**Enhanced (Customer-Managed KMS)**
```bash
# Deploy with custom KMS key for enhanced security
cdk deploy --context kmsKeyArn="arn:aws:kms:us-east-1:123456789012:key/YOUR_KEY_ID"
```

## 💰 Cost Optimization

### Serverless Benefits
- **No persistent infrastructure costs** - pay only for actual usage
- **Auto-scaling** - scales to zero when not in use
- **Optimized resource allocation** - right-sized Lambda memory and DynamoDB capacity

### Typical Monthly Costs
For 1000 Bedrock API calls/day:
- Lambda executions: ~$2-5
- DynamoDB operations: ~$1-3  
- CloudWatch logs: ~$1-2
- S3 storage: ~$0.50
- **Total**: ~$5-10/month

### Cost Monitoring
The system tracks its own operational costs and can alert when AWS service costs exceed thresholds.

## 🔄 Maintenance

### Regular Tasks
```bash
# Monthly: Update CDK and dependencies
npm update -g aws-cdk
cd app && pip install -r requirements.txt --upgrade

# Quarterly: Review parameter configurations
aws ssm describe-parameters \
  --parameter-filters "Key=Name,Option=BeginsWith,Values=/bedrock-budgeteer/"

# As needed: Review CloudWatch logs for issues
aws logs describe-log-groups \
  --log-group-name-prefix "/aws/lambda/bedrock-budgeteer"
```

### Backup & Recovery
```bash
# Backup DynamoDB tables
aws dynamodb create-backup \
  --table-name bedrock-budgeteer-user-budgets \
  --backup-name "user-budgets-$(date +%Y%m%d)"

# Export parameter configurations
aws ssm get-parameters-by-path \
  --path "/bedrock-budgeteer/" \
  --recursive > parameters-backup-$(date +%Y%m%d).json
```

## 📈 Monitoring & Alerting

### Built-in Dashboards
Access CloudWatch dashboards for:
- **System Overview**: Lambda metrics, DynamoDB performance
- **Business Metrics**: Budget violations, user activity, costs
- **Operational Health**: Error rates, latencies, system status

### Custom Alerts
```bash
# Set up custom budget alert threshold
aws cloudwatch put-metric-alarm \
  --alarm-name "HighBedrockCosts" \
  --alarm-description "Alert when Bedrock costs exceed $100/day" \
  --metric-name "TotalSpendUSD" \
  --namespace "BedrockBudgeteer" \
  --statistic "Sum" \
  --period 86400 \
  --threshold 100 \
  --comparison-operator "GreaterThanThreshold"
```

## 🚨 Emergency Procedures


### Manual User Restoration
```bash
# Restore suspended user immediately
aws dynamodb update-item \
  --table-name bedrock-budgeteer-user-budgets \
  --key '{"principal_id": {"S": "BedrockAPIKey-USERID"}}' \
  --update-expression "SET #status = :active, spent_usd = :zero" \
  --expression-attribute-names '{"#status": "status"}' \
  --expression-attribute-values '{":active": {"S": "active"}, ":zero": {"N": "0"}}'
```

### System Health Check
```bash
# Quick system health verification
aws lambda invoke \
  --function-name bedrock-budgeteer-budget-monitor \
  --payload '{"test": true}' \
  response.json && cat response.json
```

## 📚 Additional Resources

### Documentation
- **[System Architecture](docs/system-architecture.md)** - Detailed technical architecture
- **[Deployment Guide](docs/deployment-guide.md)** - Complete deployment instructions
- **[SSM Parameters](docs/ssm-parameter-hierarchy.md)** - Configuration parameters reference
- **[API Reference](docs/api-reference.md)** - API and function reference
- **[Testing Strategy](docs/testing-strategy.md)** - Testing approaches and examples

### Enterprise Features
- **Multi-region deployment** support
- **Custom notification channels** (Slack, webhooks)
- **Advanced analytics** and reporting
- **Compliance logging** and audit trails
- **Integration APIs** for external systems

### Community
- Report issues: [GitHub Issues]
- Feature requests: [GitHub Discussions]  
- Security issues: [Security Policy]

## 📄 License

[Add your license information here]

---

## 🎉 Quick Start Summary

1. **Install**: CDK CLI, Python 3.11+, AWS CLI
2. **Bootstrap**: `cdk bootstrap aws://ACCOUNT/REGION`  
3. **Deploy**: `cdk deploy`
4. **Configure**: Set notification email and adjust budgets via SSM parameters
5. **Monitor**: Use CloudWatch dashboards and alerts

**That's it!** Your Bedrock API usage is now automatically monitored and controlled.

---

**Need Help?** Check the troubleshooting section above or review the comprehensive documentation in the `/docs` folder.