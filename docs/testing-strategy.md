---
title: Testing Strategy
nav_order: 8
---

# Testing Strategy for Bedrock Budgeteer

## Overview
Comprehensive testing strategy covering unit tests, integration tests, and validation procedures for the CDK infrastructure and application components.

## Testing Levels

### 1. Unit Tests (CDK Infrastructure)
**Purpose**: Validate CloudFormation template synthesis and resource configurations
**Framework**: pytest + aws_cdk.assertions
**Location**: `app/tests/unit/`

#### Test Categories

##### Stack Synthesis Tests
- Verify stack synthesizes without errors
- Validate resource counts and types
- Check environment-specific configurations

##### Resource Configuration Tests
- DynamoDB table properties and GSIs
- IAM roles and policy attachments
- CloudWatch log groups and retention
- SNS topics and subscriptions
- SSM parameters and values

##### Security Tests
- IAM permission validation
- Encryption configuration verification
- Resource access patterns

##### Compliance Tests
- Required tag validation
- Removal policy verification
- Environment isolation checks

#### Running Unit Tests
```bash
cd app
python -m pytest tests/unit/ -v
```

### 2. Integration Tests
**Purpose**: Test component interactions and AWS service integrations
**Framework**: pytest + boto3
**Location**: `app/tests/integration/`

#### Test Categories

##### Service Integration Tests
- Lambda → DynamoDB operations
- EventBridge → Lambda triggers
- Step Functions → Lambda invocations

##### Configuration Tests
- SSM Parameter Store access
- Environment-specific behavior
- Cross-service communication

##### Monitoring Tests
- CloudWatch metrics collection
- Alarm trigger validation
- Dashboard functionality

#### Running Integration Tests
```bash
cd app
AWS_PROFILE=dev python -m pytest tests/integration/ -v
```

### 3. End-to-End Tests
**Purpose**: Validate complete workflows in deployed environments
**Framework**: pytest + boto3 + custom test harness
**Location**: `tests/e2e/`

#### Test Scenarios
- User budget setup and monitoring
- Usage tracking and cost calculation
- Budget threshold alerts
- Account suspension workflow
- Budget restoration process
- AgentCore lifecycle detection and budget initialization
- AgentCore usage attribution via role ARN matching
- AgentCore suspension and restoration workflows

### 4. AgentCore Test Coverage

**Purpose**: Validate AgentCore budgeting feature including Lambda code, CDK constructs, IAM utilities, feature flags, and usage routing
**Framework**: pytest + moto + aws_cdk.assertions
**Location**: `app/tests/unit/`
**Total**: 64 tests across 6 test files

#### Test Files

##### test_agentcore_setup.py (11 tests)
- Agent lifecycle event detection (CreateAgent, UpdateAgent)
- Budget record initialization with default limits
- Agent-to-role-ARN mapping persistence
- Duplicate agent handling and idempotency
- Invalid event payload handling

##### test_agentcore_budget_monitor.py (13 tests)
- Scheduled scan of agent budgets (5-minute interval)
- Threshold evaluation (warning at 70%, critical at 90%, exceeded at 100%)
- Grace period initiation and expiry logic
- Suspension event publishing to EventBridge
- Budget refresh date detection and restoration event publishing

##### test_agentcore_budget_manager.py (10 tests)
- Budget limit creation and updates
- Budget period reset logic
- Spent amount accumulation and tracking
- Status transitions (active, warning, grace_period, suspended)
- Budget refresh period configuration

##### test_agentcore_iam_utilities.py (14 tests)
- Execution role policy attachment and detachment
- Policy backup before suspension
- Policy restoration from backup
- Error handling for missing roles and policies
- Cross-account role ARN validation

##### test_agentcore_usage_routing.py (12 tests)
- Role ARN extraction from Bedrock usage events
- Role ARN matching to agent budget records
- Cost attribution to correct agent budget
- Fallback behavior when no agent match found (route to user budget)
- Multi-agent concurrent usage tracking

##### test_agentcore_stack.py (3 tests)
- CDK construct synthesis with AgentCore feature flag enabled
- CDK construct synthesis with AgentCore feature flag disabled (no resources created)
- Resource count and type validation for AgentCore construct

#### Test Categories Summary

| Category | Files | Tests | Description |
|----------|-------|-------|-------------|
| Lambda Code Validation | 4 | 46 | Business logic for setup, monitoring, budget management, usage routing |
| CDK Construct | 1 | 3 | Infrastructure synthesis and feature flag gating |
| IAM Utilities | 1 | 14 | Role policy operations for suspension/restoration |
| Feature Flag | 1 | 1 | Construct disabled when feature flag is off (subset of stack tests) |

#### Running AgentCore Tests
```bash
cd app
# Run all AgentCore tests
python -m pytest tests/unit/ -v -k "agentcore"

# Run a specific AgentCore test file
python -m pytest tests/unit/test_agentcore_setup.py -v
```

## Test Data Management

### Synthetic Data Generation
```python
# Example test data factory
class TestDataFactory:
    @staticmethod
    def create_test_user(user_id: str = None) -> dict:
        return {
            "user_id": user_id or f"test-user-{uuid.uuid4()}",
            "budget_limit": 100.00,
            "current_usage": 0.00,
            "status": "active",
            "created_at": datetime.utcnow().isoformat()
        }
    
    @staticmethod
    def create_usage_event(user_id: str, service: str = "bedrock") -> dict:
        return {
            "user_id": user_id,
            "service_name": service,
            "operation": "InvokeModel",
            "cost": round(random.uniform(0.01, 1.00), 4),
            "timestamp": datetime.utcnow().isoformat()
        }
```

### Test Environment Isolation
- Use separate AWS accounts for testing
- Environment-specific test data cleanup
- Isolated DynamoDB tables with test prefixes

## Test Automation

### CI/CD Integration
```yaml
# .github/workflows/test.yml
name: Test Suite
on: [push, pull_request]

jobs:
  unit-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Setup Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      - name: Install dependencies
        run: |
          cd app
          pip install -r requirements.txt
          pip install -r requirements-dev.txt
      - name: Run unit tests
        run: |
          cd app
          python -m pytest tests/unit/ -v --cov=app --cov-report=xml
      - name: Upload coverage
        uses: codecov/codecov-action@v3

  integration-tests:
    needs: unit-tests
    runs-on: ubuntu-latest
    if: github.ref == 'refs/heads/main'
    steps:
      - uses: actions/checkout@v3
      - name: Configure AWS credentials
        uses: aws-actions/configure-aws-credentials@v2
        with:
          aws-access-key-id: ${{ secrets.AWS_ACCESS_KEY_ID }}
          aws-secret-access-key: ${{ secrets.AWS_SECRET_ACCESS_KEY }}
          aws-region: us-west-2
      - name: Run integration tests
        run: |
          cd app
          python -m pytest tests/integration/ -v
```

### Pre-commit Hooks
```yaml
# .pre-commit-config.yaml
repos:
  - repo: local
    hooks:
      - id: unit-tests
        name: Run unit tests
        entry: bash -c 'cd app && python -m pytest tests/unit/ --tb=short'
        language: system
        pass_filenames: false
        always_run: true
```

## Test Validation Criteria

### Unit Test Requirements
- **Coverage**: Minimum 80% code coverage
- **Performance**: Tests complete in < 30 seconds
- **Reliability**: No flaky tests, 100% pass rate
- **Maintainability**: Clear test names and documentation

### Integration Test Requirements
- **Environment**: Test against deployed dev environment
- **Data**: Use synthetic test data only
- **Cleanup**: Automated test data cleanup
- **Isolation**: Tests can run in parallel without conflicts

### Security Test Requirements
- **IAM**: Validate least-privilege permissions
- **Encryption**: Verify data encryption at rest/transit
- **Access**: Test unauthorized access prevention
- **Compliance**: Validate SOC2/GDPR requirements

## Test Infrastructure

### Test Dependencies
```txt
# requirements-dev.txt
pytest>=7.4.0
pytest-cov>=4.1.0
pytest-mock>=3.11.0
moto>=4.2.0  # AWS service mocking
aws-cdk-lib>=2.211.0
boto3>=1.35.0
```

### Mock Services
```python
# Example using moto for AWS service mocking
import boto3
from moto import mock_dynamodb, mock_ssm

@mock_dynamodb
@mock_ssm
def test_parameter_access():
    # Create mock AWS resources
    dynamodb = boto3.resource('dynamodb', region_name='us-west-2')
    ssm = boto3.client('ssm', region_name='us-west-2')
    
    # Test logic with mocked services
    pass
```

### Test Utilities
```python
# tests/utils/helpers.py
class TestHelper:
    @staticmethod
    def wait_for_stack_status(stack_name: str, status: str, timeout: int = 300):
        """Wait for CloudFormation stack to reach specified status"""
        pass
    
    @staticmethod
    def cleanup_test_resources(environment: str):
        """Clean up test resources in specified environment"""
        pass
    
    @staticmethod
    def validate_tags(resource_arn: str, expected_tags: dict):
        """Validate resource tags match expected values"""
        pass
```

## Performance Testing

### Load Testing
- Simulate high-volume usage events
- Test DynamoDB capacity scaling
- Validate Lambda concurrency limits
- Monitor CloudWatch metrics under load

### Stress Testing
- Test system behavior at limits
- Validate error handling and recovery
- Test backup and restore procedures
- Verify monitoring and alerting

## Security Testing

### Penetration Testing
- Test IAM permission boundaries
- Validate network security controls
- Test encryption implementation
- Verify audit trail integrity

### Compliance Testing
- SOC2 control validation
- GDPR data protection verification
- Audit log completeness
- Access control validation

## Continuous Improvement

### Test Metrics
- Test execution time trends
- Code coverage trends
- Defect escape rates
- Test reliability metrics

### Test Review Process
- Regular test suite review
- Test case effectiveness analysis
- Performance bottleneck identification
- Security test gap analysis

### Documentation Updates
- Keep test documentation current
- Update test procedures for new features
- Maintain test environment documentation
- Document known issues and workarounds
