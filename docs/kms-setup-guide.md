# KMS Key Setup Guide for Bedrock Budgeteer

## Overview

By default, Bedrock Budgeteer uses **AWS-managed encryption (SSE)** for all services to minimize setup complexity and costs. However, for enhanced security and compliance requirements, you can optionally provide your own **Customer-Managed KMS Key**.

## Default Encryption Strategy

### AWS-Managed Encryption (Default)
When you deploy Bedrock Budgeteer **without** specifying a KMS key:

- **DynamoDB Tables**: Use `AWS_MANAGED` encryption (SSE)
- **S3 Buckets**: Use `S3_MANAGED` encryption (SSE-S3)
- **CloudTrail**: Uses S3 bucket encryption settings
- **SSM Parameters**: Standard parameters (no encryption for non-sensitive data)

### Customer-Managed KMS (Optional)
When you provide a KMS key during deployment:

- **DynamoDB Tables**: Use `CUSTOMER_MANAGED` encryption with your key
- **S3 Buckets**: Use `KMS` encryption with your key
- **CloudTrail**: Uses your KMS key for CloudTrail logs
- **SSM Parameters**: SecureString parameters encrypted with your key

## Creating a Customer-Managed KMS Key

### Step 1: Create the KMS Key

```bash
# Create a new KMS key for Bedrock Budgeteer
aws kms create-key \
  --description "Bedrock Budgeteer Customer-Managed Key" \
  --key-usage ENCRYPT_DECRYPT \
  --key-spec SYMMETRIC_DEFAULT \
  --region us-east-1

# Note the KeyId from the response
export KMS_KEY_ID="arn:aws:kms:us-east-1:123456789012:key/12345678-1234-1234-1234-123456789012"
```

### Step 2: Create a Key Alias (Recommended)

```bash
# Create an alias for easier management
aws kms create-alias \
  --alias-name alias/bedrock-budgeteer \
  --target-key-id $KMS_KEY_ID
```

### Step 3: Configure Key Policy

Create a key policy that allows Bedrock Budgeteer roles to use the key:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "Enable IAM User Permissions",
      "Effect": "Allow",
      "Principal": {
        "AWS": "arn:aws:iam::123456789012:root"
      },
      "Action": "kms:*",
      "Resource": "*"
    },
    {
      "Sid": "Allow Bedrock Budgeteer Service Access",
      "Effect": "Allow",
      "Principal": {
        "AWS": [
          "arn:aws:iam::123456789012:role/bedrock-budgeteer-production-lambda-execution",
          "arn:aws:iam::123456789012:role/bedrock-budgeteer-production-step-functions",
          "arn:aws:iam::123456789012:role/bedrock-budgeteer-production-firehose-delivery"
        ]
      },
      "Action": [
        "kms:Encrypt",
        "kms:Decrypt",
        "kms:ReEncrypt*",
        "kms:GenerateDataKey*",
        "kms:DescribeKey"
      ],
      "Resource": "*"
    },
    {
      "Sid": "Allow AWS Services",
      "Effect": "Allow",
      "Principal": {
        "Service": [
          "dynamodb.amazonaws.com",
          "s3.amazonaws.com",
          "firehose.amazonaws.com",
          "lambda.amazonaws.com",
          "states.amazonaws.com"
        ]
      },
      "Action": [
        "kms:Encrypt",
        "kms:Decrypt",
        "kms:ReEncrypt*",
        "kms:GenerateDataKey*",
        "kms:DescribeKey"
      ],
      "Resource": "*"
    }
  ]
}
```

Apply the key policy:

```bash
# Save the policy to a file
cat > kms-policy.json << 'EOF'
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "Enable IAM User Permissions",
      "Effect": "Allow",
      "Principal": {
        "AWS": "arn:aws:iam::123456789012:root"
      },
      "Action": "kms:*",
      "Resource": "*"
    },
    {
      "Sid": "Allow Bedrock Budgeteer Service Access",
      "Effect": "Allow",
      "Principal": {
        "AWS": [
          "arn:aws:iam::123456789012:role/bedrock-budgeteer-production-lambda-execution",
          "arn:aws:iam::123456789012:role/bedrock-budgeteer-production-step-functions",
          "arn:aws:iam::123456789012:role/bedrock-budgeteer-production-firehose-delivery"
        ]
      },
      "Action": [
        "kms:Encrypt",
        "kms:Decrypt",
        "kms:ReEncrypt*",
        "kms:GenerateDataKey*",
        "kms:DescribeKey"
      ],
      "Resource": "*"
    },
    {
      "Sid": "Allow AWS Services",
      "Effect": "Allow",
      "Principal": {
        "Service": [
          "dynamodb.amazonaws.com",
          "s3.amazonaws.com",
          "firehose.amazonaws.com",
          "lambda.amazonaws.com",
          "states.amazonaws.com"
        ]
      },
      "Action": [
        "kms:Encrypt",
        "kms:Decrypt",
        "kms:ReEncrypt*",
        "kms:GenerateDataKey*",
        "kms:DescribeKey"
      ],
      "Resource": "*"
    }
  ]
}
EOF

# Apply the policy (replace with your actual key ID and account)
aws kms put-key-policy \
  --key-id $KMS_KEY_ID \
  --policy-name default \
  --policy file://kms-policy.json
```

## Deploying with a Custom KMS Key

### Option 1: Using CDK Deploy with Context

```bash
# Set the KMS key ARN in CDK context
cdk deploy --context kmsKeyArn="arn:aws:kms:us-east-1:123456789012:key/12345678-1234-1234-1234-123456789012"
```

### Option 2: Using Environment Variables

```bash
# Set environment variable
export BEDROCK_BUDGETEER_KMS_KEY_ARN="arn:aws:kms:us-east-1:123456789012:key/12345678-1234-1234-1234-123456789012"

# Deploy
cdk deploy
```

### Option 3: Programmatic Deployment

```python
#!/usr/bin/env python3
import aws_cdk as cdk
from aws_cdk import aws_kms as kms
from app.app_stack import BedrockBudgeteerStack

app = cdk.App()

# Reference existing KMS key
existing_key = kms.Key.from_key_arn(
    app, "ExistingKMSKey",
    key_arn="arn:aws:kms:us-east-1:123456789012:key/12345678-1234-1234-1234-123456789012"
)

# Deploy with custom KMS key
BedrockBudgeteerStack(
    app, "BedrockBudgeteer",
    environment_name="production",
    kms_key=existing_key,
    env=cdk.Environment(
        account="123456789012",
        region="us-east-1"
    )
)

app.synth()
```

## Required IAM Permissions

### For the Deployment Role

Your CDK deployment role needs these additional permissions when using a custom KMS key:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "kms:DescribeKey",
        "kms:GetKeyPolicy",
        "kms:ListKeyPolicies",
        "kms:ListResourceTags"
      ],
      "Resource": "arn:aws:kms:*:*:key/*"
    },
    {
      "Effect": "Allow",
      "Action": [
        "iam:CreateRole",
        "iam:PutRolePolicy",
        "iam:AttachRolePolicy",
        "iam:PassRole"
      ],
      "Resource": "arn:aws:iam::*:role/bedrock-budgeteer-*"
    }
  ]
}
```

### For Bedrock Budgeteer Service Roles

The following roles will be automatically created with the necessary KMS permissions when you deploy with a custom key:

1. **Lambda Execution Role** (`bedrock-budgeteer-production-lambda-execution`)
   - Permissions: `kms:Decrypt`, `kms:DescribeKey`
   - Purpose: Decrypt environment variables and data

2. **Step Functions Role** (`bedrock-budgeteer-production-step-functions`)
   - Permissions: `kms:Encrypt`, `kms:Decrypt`, `kms:GenerateDataKey*`
   - Purpose: Access encrypted DynamoDB data

3. **Firehose Delivery Role** (`bedrock-budgeteer-production-firehose-delivery`)
   - Permissions: `kms:Encrypt`, `kms:GenerateDataKey*`
   - Purpose: Encrypt data written to S3

## Cost Considerations

### AWS-Managed Encryption (Default)
- **Cost**: No additional charges
- **Key Management**: Handled by AWS
- **Compliance**: Basic encryption at rest

### Customer-Managed KMS
- **Key Cost**: ~$1.00/month per key
- **API Requests**: $0.03 per 10,000 requests
- **Key Management**: Your responsibility
- **Compliance**: Full control and audit trail

### Cost Optimization Tips

1. **Single Key Strategy**: Use one KMS key for all Bedrock Budgeteer services
2. **Key Rotation**: Enable automatic rotation (included in monthly cost)
3. **Monitoring**: Set up CloudWatch alarms for unusual KMS usage
4. **Regional**: Create keys in your primary region only

## Security Best Practices

### Key Policy Security
1. **Principle of Least Privilege**: Only grant necessary permissions
2. **Resource Conditions**: Use resource-based conditions when possible
3. **Regular Audits**: Review key policies quarterly
4. **Separation of Duties**: Different roles for key administration vs usage

### Operational Security
1. **Key Rotation**: Enable automatic annual rotation
2. **Access Logging**: Monitor CloudTrail for key usage
3. **Backup Strategy**: Export key material if required for compliance
4. **Multi-Region**: Consider cross-region key replication for DR

### Compliance Considerations
1. **GDPR**: Customer-managed keys provide better data sovereignty
2. **SOC 2**: Enhanced audit trail and access controls
3. **HIPAA**: Required for healthcare data
4. **FedRAMP**: May be required for government workloads

## Troubleshooting

### Common Issues

#### 1. Key Policy Errors
```bash
# Error: AccessDenied when creating resources
# Solution: Update key policy to include service principals

aws kms get-key-policy \
  --key-id alias/bedrock-budgeteer \
  --policy-name default
```

#### 2. Cross-Region Key Issues
```bash
# Error: Key not found in deployment region
# Solution: Ensure key exists in target region or use alias

aws kms describe-key \
  --key-id alias/bedrock-budgeteer \
  --region us-east-1
```

#### 3. IAM Permission Issues
```bash
# Error: Cannot assume role or access key
# Solution: Check IAM role trust policies and permissions

aws sts get-caller-identity
aws iam get-role --role-name bedrock-budgeteer-production-lambda-execution
```

### Validation Commands

```bash
# Verify key exists and is accessible
aws kms describe-key --key-id alias/bedrock-budgeteer

# Test encryption/decryption
aws kms encrypt \
  --key-id alias/bedrock-budgeteer \
  --plaintext "test-data" \
  --query CiphertextBlob \
  --output text

# Check key policy
aws kms get-key-policy \
  --key-id alias/bedrock-budgeteer \
  --policy-name default \
  --query Policy \
  --output text | jq .
```

## Migration Scenarios

### From AWS-Managed to Customer-Managed

1. **Create KMS Key**: Follow setup instructions above
2. **Update Deployment**: Redeploy with KMS key parameter
3. **Data Migration**: AWS will re-encrypt data automatically
4. **Validation**: Verify all services are using the new key

### From Customer-Managed to AWS-Managed

1. **Remove KMS Key**: Redeploy without KMS key parameter
2. **Data Migration**: AWS will re-encrypt with AWS-managed keys
3. **Cleanup**: Optionally delete the custom KMS key
4. **Cost Verification**: Confirm KMS charges are removed

## Support and Monitoring

### CloudWatch Metrics
Monitor these KMS metrics:
- `NumberOfRequestsSucceeded`
- `NumberOfRequestsFailed`
- `KeyUsage`

### Alarms Setup
```bash
# Create alarm for KMS key usage
aws cloudwatch put-metric-alarm \
  --alarm-name "BedrockBudgeteer-KMS-HighUsage" \
  --alarm-description "High KMS key usage" \
  --metric-name NumberOfRequestsSucceeded \
  --namespace AWS/KMS \
  --statistic Sum \
  --period 3600 \
  --threshold 10000 \
  --comparison-operator GreaterThanThreshold \
  --dimensions Name=KeyId,Value=$KMS_KEY_ID
```

### Cost Monitoring
Track KMS costs in AWS Cost Explorer:
- Filter by Service: "AWS Key Management Service"
- Group by: Resource
- Monitor monthly trends

For additional support, refer to the main [Deployment Guide](deployment-guide.md) or contact your AWS solutions architect.
