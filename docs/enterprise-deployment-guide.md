# Enterprise Deployment Guide for Bedrock Budgeteer

## Overview
This guide covers deploying Bedrock Budgeteer in enterprise AWS environments with Service Control Policies (SCPs) and other organizational restrictions.

## Common Enterprise Restrictions

### Service Control Policies (SCPs)
Many enterprise AWS organizations implement SCPs that restrict certain S3 operations, particularly:
- `s3:PutBucketPublicAccessBlock` - Prevents modification of S3 public access block settings
- `s3:PutBucketAcl` - Restricts bucket ACL modifications
- `s3:PutObjectAcl` - Restricts object ACL modifications

These policies are often implemented because the organization already enforces S3 security at the organizational level, making individual bucket-level policies redundant.

## Enterprise Configuration

### Configuration Method
Enterprise deployments can be configured using CDK context variables or environment variables to enable SCP-friendly features.

### Key Configuration Options

#### Enterprise Feature Flags
For enterprise environments with SCPs, enable the following feature flag:

**Via CDK Context:**
```bash
npx cdk deploy -c bedrock-budgeteer:feature-flags.skip-s3-public-access-block=true
```

**Via Environment Variable:**
```bash
export CDK_CONTEXT_skip_s3_public_access_block=true
npx cdk deploy
```

**Via cdk.json modification:**
```json
{
  "context": {
    "bedrock-budgeteer:feature-flags": {
      "skip-s3-public-access-block": true
    }
  }
}
```

This flag instructs the CDK constructs to skip applying S3 public access block configurations, allowing deployment in environments where SCPs already enforce these restrictions.

## Deployment Instructions

### Prerequisites
1. AWS CLI configured with appropriate profile
2. CDK CLI installed (`npm install -g aws-cdk`)
3. Python 3.11+ environment
4. Appropriate IAM permissions (see below)

### Required IAM Permissions
For enterprise environments, ensure your deployment role has:

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
        "ssm:*",
        "logs:*",
        "events:*",
        "states:*",
        "sns:*",
        "kms:*",
        "cloudtrail:*",
        "kinesis:*",
        "firehose:*"
      ],
      "Resource": "*"
    }
  ]
}
```

**Note**: Some actions may be restricted by SCPs. The `skip-s3-public-access-block` flag addresses the most common restriction.

### Bootstrap Process

#### Standard Bootstrap (if no SCPs)
```bash
# Standard bootstrap
npx cdk bootstrap --profile your-profile
```

#### Enterprise Bootstrap (with SCPs)
```bash
# Enterprise bootstrap with SCP-friendly configuration
npx cdk bootstrap -c bedrock-budgeteer:feature-flags.skip-s3-public-access-block=true --profile your-profile
```

### Deployment Process

#### Using Enterprise Configuration

**Method 1: CDK Context Flag**
```bash
# Synthesize template with enterprise configuration
npx cdk synth -c bedrock-budgeteer:feature-flags.skip-s3-public-access-block=true --profile your-profile

# Deploy with enterprise configuration
npx cdk deploy -c bedrock-budgeteer:feature-flags.skip-s3-public-access-block=true --profile your-profile
```

**Method 2: Environment Variables**
```bash
# Set enterprise mode via environment
export CDK_CONTEXT_skip_s3_public_access_block=true
npx cdk deploy --profile your-profile
```

**Method 3: Modify cdk.json**
Update your `cdk.json` file to include the enterprise feature flags permanently, then deploy normally:
```bash
npx cdk deploy --profile your-profile
```

## Troubleshooting

### Common Issues

#### 1. S3 Public Access Block Errors
**Error**: `User is not authorized to perform: s3:PutBucketPublicAccessBlock`

**Solution**: Use the enterprise configuration with `skip-s3-public-access-block: true`

#### 2. Bootstrap Bucket Already Exists
**Error**: `cdk-hnb659fds-assets-xxx already exists`

**Solution**: This indicates a partial bootstrap. Clean up and retry:
```bash
# Delete the failed CloudFormation stack
aws cloudformation delete-stack --stack-name CDKToolkit --profile your-profile

# Wait for deletion to complete, then retry bootstrap
npx cdk bootstrap -c bedrock-budgeteer:feature-flags.skip-s3-public-access-block=true --profile your-profile
```

#### 3. IAM Policy Restrictions
**Error**: Various IAM permission errors

**Solution**: Work with your AWS administrators to ensure the deployment role has sufficient permissions, or use a role with broader permissions for initial deployment.

### Validation Steps

#### 1. Verify Configuration Loading
```bash
# Check that enterprise configuration is loaded
npx cdk context
```

#### 2. Validate Template Generation
```bash
# Generate template and verify S3 buckets don't have PublicAccessBlockConfiguration
npx cdk synth -c bedrock-budgeteer:feature-flags.skip-s3-public-access-block=true | grep -A 10 -B 5 "AWS::S3::Bucket"
```

#### 3. Test Deployment
```bash
# Dry run deployment
npx cdk diff -c bedrock-budgeteer:feature-flags.skip-s3-public-access-block=true --profile your-profile
```

## Configuration Reference

### Feature Flags

| Flag | Default | Enterprise | Description |
|------|---------|------------|-------------|
| `skip-s3-public-access-block` | `false` | `true` | Skip S3 public access block configuration |
| `enable-encryption` | `true` | `true` | Enable encryption at rest |
| `enable-point-in-time-recovery` | `true` | `true` | Enable DynamoDB point-in-time recovery |
| `enable-multi-az` | `false` | `false` | Enable multi-AZ deployment |

### Budget Configuration

Both configurations support minimal budget settings for testing:

```json
{
  "budget-limits": {
    "default-user-budget": 1,
    "max-user-budget": 3
  }
}
```

## Security Considerations

### S3 Security
When `skip-s3-public-access-block` is enabled:
- S3 buckets rely on organizational SCPs for public access protection
- Bucket policies and ACLs are still configured for security
- `public_read_access: false` is always enforced

### Encryption
- KMS encryption is supported in enterprise environments
- S3-managed encryption is used as fallback
- DynamoDB encryption at rest is enabled by default

### IAM Policies
- Least-privilege principles are maintained
- Resource-specific ARNs are used where possible
- Service-linked roles are preferred

## Migration from Standard to Enterprise

### Step 1: Backup Current Configuration
```bash
cp cdk.json cdk-standard-backup.json
```

### Step 2: Update Configuration
Update your `cdk.json` file to include enterprise feature flags:
```json
{
  "context": {
    "bedrock-budgeteer:feature-flags": {
      "skip-s3-public-access-block": true
    }
  }
}
```

### Step 3: Redeploy
```bash
npx cdk diff --profile your-profile
npx cdk deploy --profile your-profile
```

## Support and Troubleshooting

### Logs and Monitoring
- CloudWatch logs are available for all Lambda functions
- CloudTrail integration provides audit trails
- SNS notifications alert on deployment issues

### Common Enterprise Patterns
1. **Centralized Logging**: All logs go to organization-wide log aggregation
2. **Centralized KMS**: Use organization-provided KMS keys
3. **Network Restrictions**: Deploy in private subnets with VPC endpoints
4. **Compliance Tagging**: Automatic compliance tags via SCPs

### Getting Help
1. Check CloudFormation stack events for detailed error messages
2. Review CloudWatch logs for runtime issues
3. Validate IAM permissions using AWS IAM Policy Simulator
4. Contact your AWS administrators for SCP-related issues

## Best Practices

### 1. Use Infrastructure as Code
- Store configuration files in version control
- Use separate configurations for different environments
- Document any organization-specific customizations

### 2. Security First
- Regularly review IAM policies and permissions
- Monitor CloudTrail logs for unusual activity
- Keep CDK and dependencies updated

### 3. Cost Management
- Use minimal budget configurations for testing
- Monitor AWS costs regularly
- Set up billing alerts

### 4. Operational Excellence
- Implement proper monitoring and alerting
- Document deployment procedures
- Test disaster recovery procedures

## Appendix

### A. Enterprise Configuration Reference
For complete enterprise configuration, modify your `cdk.json` file to include all necessary feature flags and context variables as shown in the examples above.

### B. IAM Policy Templates
See `docs/iam-policy-templates.md` for detailed IAM policy examples.

### C. Troubleshooting Checklist
1. ✅ AWS CLI configured with correct profile
2. ✅ CDK CLI installed and updated
3. ✅ Python dependencies installed
4. ✅ IAM permissions verified
5. ✅ Enterprise configuration file used
6. ✅ SCP restrictions identified and addressed
7. ✅ Bootstrap completed successfully
8. ✅ Template synthesis successful
9. ✅ Deployment completed without errors
10. ✅ Post-deployment validation passed
