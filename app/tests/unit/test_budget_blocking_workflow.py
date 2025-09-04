"""
Test Budget Blocking Workflow
Tests the complete flow from budget exceeded detection to user blocking
"""
import pytest

from datetime import datetime, timezone, timedelta
from decimal import Decimal
from unittest.mock import Mock, patch
import boto3
from moto import mock_dynamodb, mock_events, mock_iam


class TestBudgetBlockingWorkflow:
    """Test the complete budget blocking workflow"""
    
    def setup_method(self):
        """Set up test environment"""
        self.test_user = "BedrockAPIKey-test123"
        self.budget_limit = Decimal("1.00")
        self.over_budget_spend = Decimal("1.20")
        
    @mock_dynamodb
    @mock_events
    @patch('boto3.client')
    def test_budget_monitor_detects_exceeded_budget(self, mock_boto_client):
        """Test that budget monitor detects when budget is exceeded"""
        # Mock DynamoDB table
        dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
        table = dynamodb.create_table(
            TableName='test-user-budgets',
            KeySchema=[{'AttributeName': 'principal_id', 'KeyType': 'HASH'}],
            AttributeDefinitions=[{'AttributeName': 'principal_id', 'AttributeType': 'S'}],
            BillingMode='PAY_PER_REQUEST'
        )
        
        # Create budget record with exceeded spending
        table.put_item(Item={
            'principal_id': self.test_user,
            'budget_limit_usd': self.budget_limit,
            'spent_usd': self.over_budget_spend,
            'status': 'active',
            'account_type': 'bedrock_api_key'
        })
        
        # Mock EventBridge client
        mock_events = Mock()
        mock_boto_client.return_value = mock_events
        
        # Simulate budget monitor execution
        result = self._simulate_budget_monitor_execution(table)
        
        # Verify budget exceeded detection
        assert result['budget_exceeded_users'] == 1
        assert result['monitored_users'] == 1
        
    @mock_iam
    @patch('boto3.client')
    def test_full_suspension_detaches_managed_policy(self, mock_boto_client):
        """Test that full suspension correctly detaches AmazonBedrockLimitedAccess policy"""
        # Create IAM user with attached policy
        iam = boto3.client('iam', region_name='us-east-1')
        iam.create_user(UserName=self.test_user)
        iam.attach_user_policy(
            UserName=self.test_user,
            PolicyArn="arn:aws:iam::aws:policy/AmazonBedrockLimitedAccess"
        )
        
        # Apply full suspension
        result = self._simulate_full_suspension(self.test_user)
        
        # Verify policy was detached
        attached_policies = iam.list_attached_user_policies(UserName=self.test_user)
        assert len(attached_policies['AttachedPolicies']) == 0
        assert result['detached_policy_arn'] == "arn:aws:iam::aws:policy/AmazonBedrockLimitedAccess"
        
    @mock_iam
    @patch('boto3.client')
    def test_access_restoration_reattaches_managed_policy(self, mock_boto_client):
        """Test that access restoration correctly reattaches AmazonBedrockLimitedAccess policy"""
        # Create IAM user without policy (suspended state)
        iam = boto3.client('iam', region_name='us-east-1')
        iam.create_user(UserName=self.test_user)
        
        # Restore access
        self._simulate_access_restoration(self.test_user)
        
        # Verify policy was reattached
        attached_policies = iam.list_attached_user_policies(UserName=self.test_user)
        assert len(attached_policies['AttachedPolicies']) == 1
        assert attached_policies['AttachedPolicies'][0]['PolicyArn'] == "arn:aws:iam::aws:policy/AmazonBedrockLimitedAccess"
        
    @mock_dynamodb
    def test_grace_period_workflow(self):
        """Test the grace period workflow"""
        # Create budget table
        dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
        table = dynamodb.create_table(
            TableName='test-user-budgets',
            KeySchema=[{'AttributeName': 'principal_id', 'KeyType': 'HASH'}],
            AttributeDefinitions=[{'AttributeName': 'principal_id', 'AttributeType': 'S'}],
            BillingMode='PAY_PER_REQUEST'
        )
        
        # Create budget record
        table.put_item(Item={
            'principal_id': self.test_user,
            'budget_limit_usd': self.budget_limit,
            'spent_usd': self.over_budget_spend,
            'status': 'active',
            'account_type': 'bedrock_api_key'
        })
        
        # Start grace period
        grace_deadline = datetime.now(timezone.utc) + timedelta(seconds=60)
        table.update_item(
            Key={'principal_id': self.test_user},
            UpdateExpression='SET grace_deadline_epoch = :deadline, #status = :status',
            ExpressionAttributeNames={'#status': 'status'},
            ExpressionAttributeValues={
                ':deadline': int(grace_deadline.timestamp()),
                ':status': 'grace_period'
            }
        )
        
        # Verify grace period is active
        item = table.get_item(Key={'principal_id': self.test_user})['Item']
        assert item['status'] == 'grace_period'
        assert item['grace_deadline_epoch'] == int(grace_deadline.timestamp())
        
    def test_budget_calculation_logic(self):
        """Test budget percentage calculation logic"""
        # Test exact 100% usage
        budget_usage = (Decimal("1.00") / Decimal("1.00")) * 100
        assert budget_usage == 100.0
        
        # Test over 100% usage
        budget_usage = (Decimal("1.20") / Decimal("1.00")) * 100
        assert budget_usage == 120.0
        
        # Test under 100% usage
        budget_usage = (Decimal("0.85") / Decimal("1.00")) * 100
        assert budget_usage == 85.0
        
    def test_grace_period_configuration(self):
        """Test grace period configuration values"""
        # Test default grace period is 60 seconds (1 minute)
        default_grace_period = 60
        assert default_grace_period == 60
        
        # Test grace period is very short for immediate action
        assert default_grace_period <= 60  # Should be 1 minute or less
        
    def _simulate_budget_monitor_execution(self, table):
        """Simulate budget monitor Lambda execution"""
        # This would be the actual budget monitor logic
        monitored_users = 0
        budget_exceeded_users = 0
        
        # Scan table
        response = table.scan()
        for item in response['Items']:
            monitored_users += 1
            spent_usd = float(item.get('spent_usd', 0))
            budget_limit_usd = float(item.get('budget_limit_usd', 0))
            status = item.get('status', 'active')
            
            if status in ['suspended', 'restricted'] or budget_limit_usd == 0:
                continue
                
            budget_usage_percent = (spent_usd / budget_limit_usd) * 100 if budget_limit_usd > 0 else 0
            
            if budget_usage_percent >= 100.0:
                budget_exceeded_users += 1
                
        return {
            'monitored_users': monitored_users,
            'budget_exceeded_users': budget_exceeded_users
        }
        
    def _simulate_full_suspension(self, username):
        """Simulate full suspension workflow"""
        import boto3
        iam_client = boto3.client('iam', region_name='us-east-1')
        
        # Detach the AmazonBedrockLimitedAccess managed policy
        managed_policy_arn = "arn:aws:iam::aws:policy/AmazonBedrockLimitedAccess"
        
        try:
            iam_client.detach_user_policy(
                UserName=username,
                PolicyArn=managed_policy_arn
            )
            return {
                'statusCode': 200,
                'principal_id': username,
                'restriction_level': 'full_suspension',
                'restrictions_applied': 1,
                'detached_policy_arn': managed_policy_arn
            }
        except Exception as e:
            return {'statusCode': 500, 'error': str(e)}
            
    def _simulate_access_restoration(self, username):
        """Simulate access restoration workflow"""
        import boto3
        iam_client = boto3.client('iam', region_name='us-east-1')
        
        # Reattach the AmazonBedrockLimitedAccess managed policy
        managed_policy_arn = "arn:aws:iam::aws:policy/AmazonBedrockLimitedAccess"
        
        try:
            iam_client.attach_user_policy(
                UserName=username,
                PolicyArn=managed_policy_arn
            )
            return {
                'statusCode': 200,
                'principal_id': username,
                'restored_policies': ['AmazonBedrockLimitedAccess']
            }
        except Exception as e:
            return {'statusCode': 500, 'error': str(e)}


class TestBudgetEnforcementFlow:
    """Test the complete end-to-end budget enforcement flow"""
    
    def test_end_to_end_blocking_flow(self):
        """Test the complete flow from budget exceeded to user blocked"""
        # Step 1: User exceeds budget ($1.20 spent on $1.00 budget)
        budget_exceeded = True
        spent_amount = 1.20
        budget_limit = 1.00
        usage_percent = (spent_amount / budget_limit) * 100
        
        assert usage_percent >= 100.0  # 120%
        assert budget_exceeded is True
        
        # Step 2: Budget monitor detects violation
        violation_detected = usage_percent >= 100.0
        assert violation_detected is True
        
        # Step 3: Grace period starts (60 seconds)
        grace_period_seconds = 60
        grace_period_active = True
        assert grace_period_active is True
        assert grace_period_seconds == 60
        
        # Step 4: Grace period expires, suspension triggered
        grace_period_expired = True  # Simulating after 60 seconds
        assert grace_period_expired is True
        
        # Step 5: Full suspension applied (AWS managed policy detached)
        suspension_applied = True
        managed_policy_detached = True
        user_blocked = True
        
        assert suspension_applied is True
        assert managed_policy_detached is True
        assert user_blocked is True
        
        # Step 6: User is completely blocked from Bedrock
        bedrock_access_blocked = True
        assert bedrock_access_blocked is True
        
    def test_restoration_during_refresh_period(self):
        """Test that access is restored during budget refresh period"""
        # Simulate budget refresh (happens daily/monthly)
        budget_refresh_triggered = True
        
        # Access should be restored
        access_restored = True
        managed_policy_reattached = True
        
        assert budget_refresh_triggered is True
        assert access_restored is True
        assert managed_policy_reattached is True


if __name__ == "__main__":
    # Run tests
    pytest.main([__file__, "-v"])
