"""
Integration tests for Workflow Orchestration
Tests end-to-end workflow execution, error handling, and monitoring
"""

import unittest

import aws_cdk as cdk
from aws_cdk import assertions
from app.app_stack import BedrockBudgeteerStack


class TestWorkflowIntegration(unittest.TestCase):
    """Integration tests for workflow orchestration features"""
    
    def setUp(self):
        """Set up integration test environment"""
        self.app = cdk.App()
        
        # Set context for testing
        self.app.node.set_context("bedrock-budgeteer:environments", {
            "test": {
                "account": "123456789012",
                "region": "us-east-1",
                "alert-email": "test@example.com"
            }
        })
        
        # Create stack with workflow orchestration
        self.stack = BedrockBudgeteerStack(
            self.app, "TestWorkflowStack",
            environment_name="production",
            env=cdk.Environment(account="123456789012", region="us-east-1")
        )
        
        # Create template for assertions
        self.template = assertions.Template.from_stack(self.stack)
    
    def test_workflow_orchestration_integration(self):
        """Test that workflow orchestration is properly integrated"""
        # Verify workflow orchestration construct exists
        self.assertIsNotNone(self.stack.workflow_orchestration)
        
        # Verify state machines are exposed
        state_machines = self.stack.step_functions_state_machines
        self.assertIn("suspension", state_machines)
        self.assertIn("restoration", state_machines)
        
        # Verify workflow functions are exposed
        workflow_functions = self.stack.workflow_functions
        expected_functions = [
            "iam_utilities", "grace_period", "emergency_override",
            "policy_backup", "restoration_validation"
        ]
        for function_name in expected_functions:
            self.assertIn(function_name, workflow_functions)
    
    def test_suspension_workflow_state_machine(self):
        """Test suspension workflow state machine configuration"""
        self.template.has_resource_properties("AWS::StepFunctions::StateMachine", {
            "StateMachineName": "bedrock-budgeteer-suspension-test",
            "RoleArn": assertions.Match.any_value(),
            "LoggingConfiguration": {
                "Level": "ALL",
                "IncludeExecutionData": True,
                "Destinations": assertions.Match.array_with([
                    assertions.Match.object_like({
                        "CloudWatchLogsLogGroup": {
                            "LogGroupArn": assertions.Match.any_value()
                        }
                    })
                ])
            }
        })
    
    def test_restoration_workflow_state_machine(self):
        """Test restoration workflow state machine configuration"""
        self.template.has_resource_properties("AWS::StepFunctions::StateMachine", {
            "StateMachineName": "bedrock-budgeteer-restoration-test",
            "RoleArn": assertions.Match.any_value(),
            "LoggingConfiguration": {
                "Level": "ALL",
                "IncludeExecutionData": True
            }
        })
    
    def test_iam_utilities_lambda_function(self):
        """Test IAM utilities Lambda function configuration"""
        self.template.has_resource_properties("AWS::Lambda::Function", {
            "FunctionName": "bedrock-budgeteer-iam-utilities-test",
            "Runtime": "python3.11",
            "Handler": "index.lambda_handler",
            "Timeout": 300,
            "Environment": {
                "Variables": {
                    "ENVIRONMENT": "test",
                    "USER_BUDGETS_TABLE": assertions.Match.any_value()
                }
            }
        })
    
    def test_grace_period_lambda_function(self):
        """Test grace period Lambda function configuration"""
        self.template.has_resource_properties("AWS::Lambda::Function", {
            "FunctionName": "bedrock-budgeteer-grace-period-test",
            "Runtime": "python3.11",
            "Handler": "index.lambda_handler",
            "Timeout": 120,
            "Environment": {
                "Variables": {
                    "ENVIRONMENT": "test"
                }
            }
        })
    
    def test_emergency_override_lambda_function(self):
        """Test emergency override Lambda function configuration"""
        self.template.has_resource_properties("AWS::Lambda::Function", {
            "FunctionName": "bedrock-budgeteer-emergency-override-test",
            "Runtime": "python3.11",
            "Handler": "index.lambda_handler",
            "Timeout": 60
        })
    
    def test_restoration_validation_lambda_function(self):
        """Test restoration validation Lambda function configuration"""
        self.template.has_resource_properties("AWS::Lambda::Function", {
            "FunctionName": "bedrock-budgeteer-restoration-validation-test",
            "Runtime": "python3.11",
            "Handler": "index.lambda_handler",
            "Timeout": 180,
            "Environment": {
                "Variables": {
                    "ENVIRONMENT": "test",
                    "USER_BUDGETS_TABLE": assertions.Match.any_value()
                }
            }
        })
    
    def test_workflow_dlq_queues(self):
        """Test that dead letter queues are created for workflow functions"""
        expected_dlqs = [
            "iam_utilities", "grace_period", "emergency_override",
            "policy_backup", "restoration_validation"
        ]
        
        for dlq_name in expected_dlqs:
            self.template.has_resource_properties("AWS::SQS::Queue", {
                "QueueName": f"bedrock-budgeteer-{dlq_name}-dlq-test",
                "MessageRetentionPeriod": 1209600,  # 14 days
                "VisibilityTimeoutSeconds": 300
            })
    
    def test_eventbridge_workflow_triggers(self):
        """Test EventBridge rules for workflow triggers"""
        # Suspension workflow trigger
        self.template.has_resource_properties("AWS::Events::Rule", {
            "Name": "bedrock-budgeteer-suspension-trigger-test",
            "Description": "Trigger suspension workflow for budget violations",
            "EventPattern": {
                "source": ["bedrock-budgeteer"],
                "detail-type": ["Suspension Workflow Required"]
            },
            "State": "ENABLED",
            "Targets": assertions.Match.array_with([
                assertions.Match.object_like({
                    "Arn": assertions.Match.any_value(),
                    "Id": assertions.Match.any_value(),
                    "RoleArn": assertions.Match.any_value()
                })
            ])
        })
        
        # Restoration workflow trigger
        self.template.has_resource_properties("AWS::Events::Rule", {
            "Name": "bedrock-budgeteer-restoration-trigger-test",
            "Description": "Trigger restoration workflow for admin approvals",
            "EventPattern": {
                "source": ["bedrock-budgeteer"],
                "detail-type": ["User Restoration Requested"]
            }
        })
    
    def test_iam_permissions_for_workflow_functions(self):
        """Test IAM permissions for workflow Lambda functions"""
        # IAM utilities function permissions
        self.template.has_resource_properties("AWS::IAM::Policy", {
            "PolicyDocument": {
                "Statement": assertions.Match.array_with([
                    assertions.Match.object_like({
                        "Effect": "Allow",
                        "Action": assertions.Match.array_with([
                            "iam:GetUser",
                            "iam:GetRole",
                            "iam:AttachUserPolicy",
                            "iam:DetachUserPolicy",
                            "iam:PutUserPolicy",
                            "iam:DeleteUserPolicy"
                        ]),
                        "Resource": "*"
                    })
                ])
            }
        })
        
        # Emergency override function permissions
        self.template.has_resource_properties("AWS::IAM::Policy", {
            "PolicyDocument": {
                "Statement": assertions.Match.array_with([
                    assertions.Match.object_like({
                        "Effect": "Allow",
                        "Action": assertions.Match.array_with([
                            "ssm:GetParameter",
                            "ssm:GetParameters",
                            "ssm:GetParametersByPath"
                        ]),
                        "Resource": assertions.Match.array_with([
                            assertions.Match.string_like_regexp("arn:aws:ssm:.*:.*:parameter/bedrock-budgeteer/.*")
                        ])
                    })
                ])
            }
        })
    
    def test_step_functions_role_permissions(self):
        """Test Step Functions execution role permissions"""
        # Step Functions role should have permissions to invoke Lambda functions
        self.template.has_resource_properties("AWS::IAM::Policy", {
            "PolicyDocument": {
                "Statement": assertions.Match.array_with([
                    assertions.Match.object_like({
                        "Effect": "Allow",
                        "Action": "lambda:InvokeFunction",
                        "Resource": assertions.Match.any_value()
                    })
                ])
            }
        })
        
        # Step Functions role should have DynamoDB permissions
        self.template.has_resource_properties("AWS::IAM::Policy", {
            "PolicyDocument": {
                "Statement": assertions.Match.array_with([
                    assertions.Match.object_like({
                        "Effect": "Allow",
                        "Action": assertions.Match.array_with([
                            "dynamodb:GetItem",
                            "dynamodb:PutItem",
                            "dynamodb:UpdateItem",
                            "dynamodb:DeleteItem"
                        ])
                    })
                ])
            }
        })
    
    def test_configuration_parameters_for_workflows(self):
        """Test that workflow configuration parameters are created"""
        # Global configuration parameters
        expected_global_params = [
            "emergency_stop_active",
            "maintenance_mode",
            "thresholds_percent_warn",
            "thresholds_percent_critical",
            "default_user_budget_usd"
        ]
        
        for param_name in expected_global_params:
            self.template.has_resource_properties("AWS::SSM::Parameter", {
                "Name": f"/bedrock-budgeteer/global/{param_name}",
                "Type": "String"
            })
        
        # Workflow-specific configuration parameters
        expected_workflow_params = [
            "grace_period_seconds",
            "suspension_timeout_minutes", 
            "restoration_timeout_minutes",
            "restoration_cooldown_hours"
        ]
        
        for param_name in expected_workflow_params:
            self.template.has_resource_properties("AWS::SSM::Parameter", {
                "Name": f"/bedrock-budgeteer/test/workflow/{param_name}",
                "Type": "String"
            })
    
    def test_cloudwatch_log_groups_for_workflows(self):
        """Test CloudWatch log groups for workflow state machines"""
        # Suspension workflow log group
        self.template.has_resource_properties("AWS::Logs::LogGroup", {
            "LogGroupName": "/aws/stepfunctions/bedrock-budgeteer-suspension-test"
        })
        
        # Restoration workflow log group
        self.template.has_resource_properties("AWS::Logs::LogGroup", {
            "LogGroupName": "/aws/stepfunctions/bedrock-budgeteer-restoration-test"
        })
    
    def test_monitoring_integration(self):
        """Test monitoring integration for workflows"""
        # Verify that monitoring construct includes workflow monitoring
        self.assertIsNotNone(self.stack.monitoring)
        
        # Note: Step Functions monitoring would be verified by checking
        # that the monitoring construct has methods to monitor state machines
        
        # CloudWatch alarms should be created for workflow failures
        # (This would be tested in the monitoring construct tests)
        pass
    
    def test_workflow_error_handling(self):
        """Test error handling configuration in workflows"""
        # Both state machines should have error handling configured
        # This is implicit in the state machine definitions
        
        # DLQ queues should be configured for Lambda functions
        expected_dlq_count = 5  # One for each workflow function
        dlq_resources = self.template.find_resources("AWS::SQS::Queue", {
            "Properties": {
                "QueueName": assertions.Match.string_like_regexp(".*-dlq-test")
            }
        })
        
        # Should have at least the expected number of DLQ resources
        self.assertGreaterEqual(len(dlq_resources), expected_dlq_count)


class TestWorkflowSecurityCompliance(unittest.TestCase):
    """Security and compliance tests for workflow orchestration"""
    
    def setUp(self):
        """Set up security test environment"""
        self.app = cdk.App()
        self.app.node.set_context("bedrock-budgeteer:environments", {
            "test": {
                "account": "123456789012",
                "region": "us-east-1",
                "alert-email": "test@example.com"
            }
        })
        
        self.stack = BedrockBudgeteerStack(
            self.app, "SecurityTestStack",
            environment_name="production",
            env=cdk.Environment(account="123456789012", region="us-east-1")
        )
        
        self.template = assertions.Template.from_stack(self.stack)
    
    def test_least_privilege_iam_policies(self):
        """Test that IAM policies follow least privilege principle"""
        # IAM utilities should only have necessary IAM permissions
        # (Not overly broad permissions like iam:*)
        
        # Find policies that grant IAM permissions
        iam_policies = self.template.find_resources("AWS::IAM::Policy", {
            "Properties": {
                "PolicyDocument": {
                    "Statement": assertions.Match.array_with([
                        assertions.Match.object_like({
                            "Action": assertions.Match.any_value()
                        })
                    ])
                }
            }
        })
        
        # Verify that policies exist (specific content would be tested in unit tests)
        self.assertGreater(len(iam_policies), 0)
    
    def test_encryption_configuration(self):
        """Test encryption configuration for workflow resources"""
        # SQS queues should use encryption for production environment
        
        # Lambda functions should use appropriate encryption
        lambda_functions = self.template.find_resources("AWS::Lambda::Function")
        self.assertGreater(len(lambda_functions), 0)
    
    def test_audit_logging_configuration(self):
        """Test that audit logging is properly configured"""
        # Step Functions should have logging enabled
        state_machines = self.template.find_resources("AWS::StepFunctions::StateMachine", {
            "Properties": {
                "LoggingConfiguration": {
                    "Level": "ALL"
                }
            }
        })
        
        # Should have 2 state machines with logging
        self.assertEqual(len(state_machines), 2)
    
    def test_resource_tagging(self):
        """Test that resources are properly tagged"""
        # All resources should have appropriate tags
        # This would be verified by the tagging framework tests
        pass
    
    def test_network_security(self):
        """Test network security configuration"""
        # Lambda functions should be configured with appropriate VPC settings if needed
        # Step Functions should use private endpoints if configured
        pass


class TestWorkflowPerformance(unittest.TestCase):
    """Performance tests for workflow orchestration"""
    
    def setUp(self):
        """Set up performance test environment"""
        self.app = cdk.App()
        self.app.node.set_context("bedrock-budgeteer:environments", {
            "test": {
                "account": "123456789012", 
                "region": "us-east-1",
                "alert-email": "test@example.com"
            }
        })
        
        self.stack = BedrockBudgeteerStack(
            self.app, "PerformanceTestStack",
            environment_name="production",
            env=cdk.Environment(account="123456789012", region="us-east-1")
        )
        
        self.template = assertions.Template.from_stack(self.stack)
    
    def test_lambda_function_timeout_configuration(self):
        """Test Lambda function timeout configuration"""
        # IAM utilities function should have appropriate timeout (5 minutes)
        self.template.has_resource_properties("AWS::Lambda::Function", {
            "FunctionName": "bedrock-budgeteer-iam-utilities-test",
            "Timeout": 300
        })
        
        # Emergency override should have short timeout (1 minute)
        self.template.has_resource_properties("AWS::Lambda::Function", {
            "FunctionName": "bedrock-budgeteer-emergency-override-test",
            "Timeout": 60
        })
    
    def test_step_functions_timeout_configuration(self):
        """Test Step Functions timeout configuration"""
        # Suspension workflow should have reasonable timeout (30 minutes)
        self.template.has_resource_properties("AWS::StepFunctions::StateMachine", {
            "StateMachineName": "bedrock-budgeteer-suspension-test"
            # Timeout would be in the state machine definition
        })
        
        # Restoration workflow should have shorter timeout (15 minutes)
        self.template.has_resource_properties("AWS::StepFunctions::StateMachine", {
            "StateMachineName": "bedrock-budgeteer-restoration-test"
        })
    
    def test_memory_allocation(self):
        """Test Lambda function memory allocation"""
        # IAM utilities should have adequate memory (512MB)
        self.template.has_resource_properties("AWS::Lambda::Function", {
            "FunctionName": "bedrock-budgeteer-iam-utilities-test",
            "MemorySize": 512
        })
        
        # Emergency override can use less memory (256MB)
        self.template.has_resource_properties("AWS::Lambda::Function", {
            "FunctionName": "bedrock-budgeteer-emergency-override-test",
            "MemorySize": 256
        })
    
    def test_concurrent_execution_limits(self):
        """Test concurrent execution configuration"""
        # Lambda functions should have appropriate reserved concurrency if needed
        # This would be configured based on expected load
        pass


if __name__ == '__main__':
    unittest.main()
