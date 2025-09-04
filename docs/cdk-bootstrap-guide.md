# CDK Bootstrap Guide for Bedrock Budgeteer

## Overview
AWS CDK requires a bootstrap stack to be deployed in each account and region before you can deploy CDK applications. This guide covers the bootstrap process for all environments.

## Prerequisites

### Required Tools
- AWS CLI v2 configured with appropriate credentials
- AWS CDK CLI v2 installed (`npm install -g aws-cdk`)
- Python 3.11+ environment
- Appropriate IAM permissions for bootstrap operations

### Required Permissions
The AWS account/role used for bootstrapping needs these permissions:
- `iam:*` (for creating CDK toolkit roles)
- `cloudformation:*` (for creating the bootstrap stack)
- `s3:*` (for creating CDK assets bucket)
- `ssm:*` (for storing bootstrap parameters)
- `ecr:*` (for creating ECR repository if using Docker)

## Bootstrap Process

### 1. Verify CDK Installation
```bash
# Check CDK version
cdk --version

# Should output something like: 2.211.0 (build...)
```

### 2. Configure AWS Profiles
Set up AWS profiles for each environment:

```bash
# Configure profiles for each environment
aws configure --profile bedrock-budgeteer-dev
aws configure --profile bedrock-budgeteer-staging  
aws configure --profile bedrock-budgeteer-prod
```

### 3. Bootstrap Each Environment

#### Development Environment
```bash
# Bootstrap development environment
cdk bootstrap aws://111111111111/us-east-1 \
  --profile bedrock-budgeteer-dev \
  --cloudformation-execution-policies arn:aws:iam::aws:policy/AdministratorAccess \
  --toolkit-stack-name CDKToolkit-bedrock-budgeteer-dev \
  --qualifier bbdev

# Verify bootstrap
aws cloudformation describe-stacks \
  --stack-name CDKToolkit-bedrock-budgeteer-dev \
  --profile bedrock-budgeteer-dev \
  --region us-east-1
```

#### Staging Environment
```bash
# Bootstrap staging environment
cdk bootstrap aws://222222222222/us-east-1 \
  --profile bedrock-budgeteer-staging \
  --cloudformation-execution-policies arn:aws:iam::aws:policy/AdministratorAccess \
  --toolkit-stack-name CDKToolkit-bedrock-budgeteer-staging \
  --qualifier bbstaging

# Verify bootstrap
aws cloudformation describe-stacks \
  --stack-name CDKToolkit-bedrock-budgeteer-staging \
  --profile bedrock-budgeteer-staging \
  --region us-east-1
```

#### Production Environment
```bash
# Bootstrap production environment
cdk bootstrap aws://333333333333/us-east-1 \
  --profile bedrock-budgeteer-prod \
  --cloudformation-execution-policies arn:aws:iam::aws:policy/AdministratorAccess \
  --toolkit-stack-name CDKToolkit-bedrock-budgeteer-prod \
  --qualifier bbprod

# Verify bootstrap
aws cloudformation describe-stacks \
  --stack-name CDKToolkit-bedrock-budgeteer-prod \
  --profile bedrock-budgeteer-prod \
  --region us-east-1
```

## Bootstrap Parameters Explained

### Core Parameters
- `aws://ACCOUNT/REGION`: Target account and region for bootstrap
- `--profile`: AWS CLI profile to use for authentication
- `--cloudformation-execution-policies`: IAM policies for CloudFormation execution
- `--toolkit-stack-name`: Custom name for the CDK toolkit stack
- `--qualifier`: Unique identifier for this bootstrap (max 10 chars)

### Security Considerations
- **Production**: Use least-privilege policies instead of `AdministratorAccess`
- **Cross-Account**: Configure trust relationships for cross-account deployments
- **MFA**: Ensure MFA is required for production bootstrap operations

## Advanced Bootstrap Configuration

### Custom CloudFormation Execution Policies
For production environments, create custom policies instead of `AdministratorAccess`:

```bash
# Create custom execution policy ARN first, then:
cdk bootstrap aws://333333333333/us-east-1 \
  --profile bedrock-budgeteer-prod \
  --cloudformation-execution-policies arn:aws:iam::333333333333:policy/BedrockBudgeteerExecutionPolicy \
  --toolkit-stack-name CDKToolkit-bedrock-budgeteer-prod \
  --qualifier bbprod
```

### Cross-Account Deployments
If deploying from a central CI/CD account:

```bash
# Bootstrap with trust policy for CI/CD account
cdk bootstrap aws://333333333333/us-east-1 \
  --profile bedrock-budgeteer-prod \
  --trust 444444444444 \
  --cloudformation-execution-policies arn:aws:iam::aws:policy/AdministratorAccess \
  --toolkit-stack-name CDKToolkit-bedrock-budgeteer-prod \
  --qualifier bbprod
```

## Verification and Troubleshooting

### Verify Bootstrap Resources
Check that bootstrap created the required resources:

```bash
# List CDK toolkit resources
aws cloudformation list-stack-resources \
  --stack-name CDKToolkit-bedrock-budgeteer-dev \
  --profile bedrock-budgeteer-dev \
  --region us-east-1
```

Expected resources:
- **S3 Bucket**: `cdk-bbdev-assets-111111111111-us-east-1`
- **IAM Roles**: `cdk-bbdev-cfn-exec-role-111111111111-us-east-1`
- **IAM Policies**: Various CDK execution policies
- **SSM Parameters**: Bootstrap version and configuration

### Common Issues and Solutions

#### Issue: Permission Denied
```
Error: Need to perform AWS calls but no credentials found
```
**Solution**: Verify AWS profile configuration and credentials:
```bash
aws sts get-caller-identity --profile bedrock-budgeteer-dev
```

#### Issue: Bootstrap Already Exists
```
Error: Stack CDKToolkit already exists
```
**Solution**: Use `--force` to update existing bootstrap:
```bash
cdk bootstrap --force aws://111111111111/us-east-1 --profile bedrock-budgeteer-dev
```

#### Issue: Qualifier Conflicts
```
Error: Qualifier 'bbdev' is already in use
```
**Solution**: Use a different qualifier or clean up existing bootstrap:
```bash
# List existing qualifiers
aws ssm get-parameters-by-path \
  --path "/cdk-bootstrap/" \
  --profile bedrock-budgeteer-dev \
  --region us-east-1
```

### Clean Up Bootstrap (If Needed)
To remove a CDK bootstrap stack:

```bash
# Delete the CDK toolkit stack
aws cloudformation delete-stack \
  --stack-name CDKToolkit-bedrock-budgeteer-dev \
  --profile bedrock-budgeteer-dev \
  --region us-east-1

# Manually delete S3 bucket (empty it first)
aws s3 rm s3://cdk-bbdev-assets-111111111111-us-east-1 --recursive --profile bedrock-budgeteer-dev
aws s3 rb s3://cdk-bbdev-assets-111111111111-us-east-1 --profile bedrock-budgeteer-dev
```

## Deployment After Bootstrap

### Environment-Specific Deployment
After bootstrap, deploy the Bedrock Budgeteer stack:

```bash
# Development
cdk deploy --profile bedrock-budgeteer-dev -c environment=dev

# Staging  
cdk deploy --profile bedrock-budgeteer-staging -c environment=staging

# Production
cdk deploy --profile bedrock-budgeteer-prod -c environment=prod
```

### Automated Deployment Script
```bash
#!/bin/bash
# deploy.sh - Automated deployment script

ENVIRONMENT=${1:-dev}
PROFILE="bedrock-budgeteer-$ENVIRONMENT"

echo "Deploying to $ENVIRONMENT environment..."

# Synthesize template
cdk synth -c environment=$ENVIRONMENT

# Deploy with approval
cdk deploy \
  --profile $PROFILE \
  -c environment=$ENVIRONMENT \
  --require-approval never

echo "Deployment to $ENVIRONMENT completed!"
```

## Bootstrap Maintenance

### Regular Tasks
- **Monthly**: Review bootstrap stack for any drift or issues
- **Quarterly**: Update CDK toolkit to latest version
- **Annually**: Rotate IAM credentials used for bootstrap

### Updating Bootstrap
```bash
# Update to latest CDK toolkit version
cdk bootstrap --force aws://111111111111/us-east-1 --profile bedrock-budgeteer-dev
```

### Monitoring Bootstrap Health
Create CloudWatch alarms for:
- S3 bucket accessibility
- IAM role availability
- CloudFormation stack status

## Security Best Practices

### 1. Least Privilege
- Use custom execution policies in production
- Regularly audit CDK toolkit permissions
- Implement resource-based policies where applicable

### 2. Access Control
- Require MFA for bootstrap operations
- Use separate AWS accounts for each environment
- Implement SCPs to prevent unauthorized bootstrap changes

### 3. Auditing
- Enable CloudTrail for all bootstrap operations
- Monitor CDK toolkit resource usage
- Set up alerts for unauthorized changes

### 4. Backup and Recovery
- Document bootstrap configurations
- Maintain infrastructure as code for custom policies
- Test bootstrap recovery procedures regularly

## Quick Reference

### Bootstrap Commands by Environment
```bash
# Development
cdk bootstrap aws://111111111111/us-east-1 --profile bedrock-budgeteer-dev --qualifier bbdev

# Staging
cdk bootstrap aws://222222222222/us-east-1 --profile bedrock-budgeteer-staging --qualifier bbstaging

# Production
cdk bootstrap aws://333333333333/us-east-1 --profile bedrock-budgeteer-prod --qualifier bbprod
```

### Verification Commands
```bash
# Check bootstrap status
aws cloudformation describe-stacks --stack-name CDKToolkit-bedrock-budgeteer-{env} --profile bedrock-budgeteer-{env}

# List bootstrap resources
aws cloudformation list-stack-resources --stack-name CDKToolkit-bedrock-budgeteer-{env} --profile bedrock-budgeteer-{env}

# Check S3 bucket
aws s3 ls s3://cdk-{qualifier}-assets-{account}-{region} --profile bedrock-budgeteer-{env}
```
