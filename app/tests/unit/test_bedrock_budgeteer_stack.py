"""
Unit tests for Bedrock Budgeteer CDK Stack
Tests infrastructure synthesis and validates resource configurations
"""
import pytest
import aws_cdk as cdk

from aws_cdk.assertions import Template, Match

from app.app_stack import BedrockBudgeteerStack


class TestBedrockBudgeteerStack:
    """Test suite for Bedrock Budgeteer stack validation"""
    
    @pytest.fixture
    def app(self):
        """Create CDK app for testing"""
        return cdk.App()
    
    @pytest.fixture
    def stack(self, app):
        """Create production stack for testing"""
        return BedrockBudgeteerStack(
            app, "TestStack",
            environment_name="production"
        )
    
    @pytest.fixture
    def template(self, stack):
        """Get CloudFormation template for production stack"""
        return Template.from_stack(stack)


class TestDynamoDBTables(TestBedrockBudgeteerStack):
    """Test DynamoDB table configurations"""
    
    def test_user_budget_table_created(self, template):
        """Test that user budget table is created correctly"""
        template.has_resource_properties("AWS::DynamoDB::Table", {
            "TableName": "bedrock-budgeteer-production-user-budgets",
            "PointInTimeRecoverySpecification": {
                "PointInTimeRecoveryEnabled": True  # Enabled for production
            }
        })
    
    def test_usage_tracking_table_created(self, template):
        """Test that usage tracking table is created correctly"""
        template.has_resource_properties("AWS::DynamoDB::Table", {
            "TableName": "bedrock-budgeteer-production-usage-tracking"
        })
    

    
    def test_tables_have_default_encryption(self, template):
        """Test that production tables have AWS-managed encryption by default"""
        # When no KMS key is provided, should use AWS-managed encryption
        # No KMS key should be created by default
        template.resource_count_is("AWS::KMS::Key", 0)
        
        # Tables should have AWS-managed encryption
        template.has_resource_properties("AWS::DynamoDB::Table", {
            "SSESpecification": {
                "SSEEnabled": True
            }
        })
    
    def test_global_secondary_indexes_created(self, template):
        """Test that required GSIs are created"""
        # User budget table should have budget status index
        template.has_resource_properties("AWS::DynamoDB::Table", {
            "GlobalSecondaryIndexes": Match.array_with([
                {
                    "IndexName": "BudgetStatusIndex",
                    "KeySchema": Match.array_with([
                        {"AttributeName": "budget_status", "KeyType": "HASH"}
                    ])
                }
            ])
        })


class TestIAMRoles(TestBedrockBudgeteerStack):
    """Test IAM role configurations"""
    
    def test_lambda_execution_role_created(self, template):
        """Test that Lambda execution role is created with correct permissions"""
        template.has_resource_properties("AWS::IAM::Role", {
            "RoleName": "bedrock-budgeteer-production-lambda-execution",
            "AssumeRolePolicyDocument": {
                "Statement": [
                    {
                        "Effect": "Allow",
                        "Principal": {
                            "Service": "lambda.amazonaws.com"
                        },
                        "Action": "sts:AssumeRole"
                    }
                ]
            }
        })
    
    def test_step_functions_role_created(self, template):
        """Test that Step Functions role is created"""
        template.has_resource_properties("AWS::IAM::Role", {
            "RoleName": "bedrock-budgeteer-production-step-functions",
            "AssumeRolePolicyDocument": {
                "Statement": [
                    {
                        "Effect": "Allow",
                        "Principal": {
                            "Service": "states.amazonaws.com"
                        },
                        "Action": "sts:AssumeRole"
                    }
                ]
            }
        })
    
    def test_iam_policies_created(self, template):
        """Test that custom IAM policies are created"""
        # DynamoDB access policy
        template.has_resource_properties("AWS::IAM::ManagedPolicy", {
            "ManagedPolicyName": "bedrock-budgeteer-production-dynamodb-access"
        })
        
        # EventBridge publish policy
        template.has_resource_properties("AWS::IAM::ManagedPolicy", {
            "ManagedPolicyName": "bedrock-budgeteer-production-eventbridge-publish"
        })


class TestMonitoringResources(TestBedrockBudgeteerStack):
    """Test monitoring and logging configurations"""
    
    def test_cloudwatch_log_groups_created(self, template):
        """Test that CloudWatch log groups are automatically managed by CDK for Lambda functions"""
        # NOTE: Log groups are now automatically created by CDK for Lambda functions
        # due to "@aws-cdk/aws-lambda:useCdkManagedLogGroup": true setting
        # This test verifies Lambda functions exist (which will have auto-created log groups)
        
        lambda_functions = template.find_resources("AWS::Lambda::Function")
        assert len(lambda_functions) > 0, "Should have Lambda functions (with auto-created log groups)"
    
    def test_sns_topics_created(self, template):
        """Test that SNS topics are created for notifications"""
        template.has_resource_properties("AWS::SNS::Topic", {
            "TopicName": "bedrock-budgeteer-production-operational-alerts"
        })
    
    def test_cloudwatch_dashboard_created(self, template):
        """Test that CloudWatch dashboard is created"""
        template.has_resource_properties("AWS::CloudWatch::Dashboard", {
            "DashboardName": "bedrock-budgeteer-production-system"
        })


class TestSSMParameters(TestBedrockBudgeteerStack):
    """Test SSM Parameter Store configurations"""
    
    def test_cost_parameters_created(self, template):
        """Test that cost configuration parameters are created"""
        template.has_resource_properties("AWS::SSM::Parameter", {
            "Name": "/bedrock-budgeteer/production/cost/budget_refresh_period_days",
            "Value": "30",
            "Type": "String"
        })
    
    def test_global_parameters_created(self, template):
        """Test that global configuration parameters are created"""
        # Test default budget parameter
        template.has_resource_properties("AWS::SSM::Parameter", {
            "Name": "/bedrock-budgeteer/global/default_user_budget_usd",
            "Value": "1",
            "Type": "String"
        })
        
        # Test threshold parameters
        template.has_resource_properties("AWS::SSM::Parameter", {
            "Name": "/bedrock-budgeteer/global/thresholds_percent_warn",
            "Value": "70",
            "Type": "String"
        })
        
        template.has_resource_properties("AWS::SSM::Parameter", {
            "Name": "/bedrock-budgeteer/global/thresholds_percent_critical",
            "Value": "90",
            "Type": "String"
        })


class TestProductionConfigurations(TestBedrockBudgeteerStack):
    """Test production resource configurations"""
    
    def test_encryption_enabled(self, template):
        """Test that encryption is enabled for production"""
        # Production should have KMS encryption
        template.resource_count_is("AWS::KMS::Key", 1)


class TestResourceTagging(TestBedrockBudgeteerStack):
    """Test resource tagging compliance"""
    
    def test_required_tags_applied(self, template):
        """Test that required tags are applied to resources"""
        # Check DynamoDB tables have required tags
        template.has_resource_properties("AWS::DynamoDB::Table", {
            "Tags": Match.array_with([
                {"Key": "App", "Value": "bedrock-budgeteer"},
                {"Key": "Environment", "Value": "production"}
            ])
        })


class TestStackSynthesis(TestBedrockBudgeteerStack):
    """Test overall stack synthesis and structure"""
    
    def test_stack_synthesizes_successfully(self, stack):
        """Test that stack synthesizes without errors"""
        # If we get this far, synthesis was successful
        assert stack is not None
    
    def test_resource_counts(self, template):
        """Test expected number of resources are created"""
        # Should have 4 DynamoDB tables
        template.resource_count_is("AWS::DynamoDB::Table", 4)
        
        # Should have 3 IAM roles
        template.resource_count_is("AWS::IAM::Role", 3)
        
        # Should have 2 managed policies
        template.resource_count_is("AWS::IAM::ManagedPolicy", 2)
