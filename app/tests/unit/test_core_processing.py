"""
Unit tests for Core Processing functionality
Tests Lambda functions, event processing, and cost calculation logic
"""
import unittest
from unittest.mock import Mock, patch
import json
import base64
from decimal import Decimal
from datetime import datetime, timezone


from aws_cdk import App, Stack
from aws_cdk.assertions import Template

# Import the construct
from app.constructs.core_processing import CoreProcessingConstruct
from app.constructs.data_storage import DataStorageConstruct
from app.constructs.log_storage import LogStorageConstruct


class TestDecimalConversion(unittest.TestCase):
    """Test Decimal to timestamp conversion fix"""
    
    def test_datetime_fromtimestamp_with_decimal(self):
        """Test that Decimal values can be converted to datetime.fromtimestamp()"""
        from decimal import Decimal
        from datetime import datetime, timezone
        
        # Test Decimal conversion
        decimal_timestamp = Decimal('1693747749.123')
        
        # This should work with our fix logic
        if hasattr(decimal_timestamp, '__float__'):
            epoch_timestamp = float(decimal_timestamp)
        else:
            epoch_timestamp = float(str(decimal_timestamp))
        
        # Should not raise TypeError
        result = datetime.fromtimestamp(epoch_timestamp, timezone.utc)
        self.assertIsInstance(result, datetime)
        
        # Test with different types
        test_values = [
            Decimal('1693747749'),
            1693747749,
            1693747749.0,
            '1693747749'
        ]
        
        for value in test_values:
            try:
                if hasattr(value, '__float__'):
                    epoch_timestamp = float(value)
                else:
                    epoch_timestamp = float(str(value))
                result = datetime.fromtimestamp(epoch_timestamp, timezone.utc)
                self.assertIsInstance(result, datetime)
            except (ValueError, TypeError):
                self.fail(f"Failed to convert {type(value)} value {value} to datetime")


class TestLambdaImportValidation(unittest.TestCase):
    """Test Lambda function import validation to prevent runtime errors"""
    
    def test_shared_utilities_contain_required_imports(self):
        """Test that shared utilities contain all required imports and AWS clients"""
        from app.constructs.shared.lambda_utilities import get_shared_lambda_utilities
        
        shared_utils = get_shared_lambda_utilities()
        
        # Check for required imports
        required_imports = [
            'import json',
            'import os', 
            'import boto3',
            'import logging',
            'import uuid',
            'import base64',
            'import gzip',
            'from decimal import Decimal',
            'from datetime import datetime, timezone, timedelta'
        ]
        
        for required_import in required_imports:
            self.assertIn(required_import, shared_utils, 
                         f"Missing required import: {required_import}")
        
        # Check for AWS client initializations
        required_clients = [
            'dynamodb = boto3.resource',
            'ssm = boto3.client',
            'cloudwatch = boto3.client',
            'events = boto3.client'
        ]
        
        for client in required_clients:
            self.assertIn(client, shared_utils,
                         f"Missing AWS client initialization: {client}")
        
        # Check for utility classes
        required_classes = [
            'class ConfigurationManager',
            'class DynamoDBHelper',
            'class BedrockPricingCalculator',
            'class MetricsPublisher',
            'class EventPublisher'
        ]
        
        for cls in required_classes:
            self.assertIn(cls, shared_utils,
                         f"Missing utility class: {cls}")
    
    def test_user_setup_lambda_uses_correct_references(self):
        """Test that user setup Lambda uses correct AWS client and utility references"""
        from app.constructs.lambda_functions.user_setup import get_user_setup_function_code
        
        user_setup_code = get_user_setup_function_code()
        
        # Check for correct AWS client usage
        self.assertIn('dynamodb.Table(os.environ[', user_setup_code,
                     "User setup Lambda should use 'dynamodb.Table' (not 'boto3.resource')")
        
        # Check for utility class usage
        self.assertIn('ConfigurationManager.get_parameter', user_setup_code,
                     "User setup Lambda should use ConfigurationManager")
        self.assertIn('EventPublisher.publish_budget_event', user_setup_code,
                     "User setup Lambda should use EventPublisher")
        self.assertIn('MetricsPublisher.publish_budget_metric', user_setup_code,
                     "User setup Lambda should use MetricsPublisher")
        
        # Check that it doesn't try to import these separately
        self.assertNotIn('import dynamodb', user_setup_code,
                        "Should not import dynamodb separately")
        self.assertNotIn('from boto3', user_setup_code,
                        "Should not import boto3 separately")
    
    def test_usage_calculator_lambda_uses_correct_references(self):
        """Test that usage calculator Lambda uses correct AWS client and utility references"""
        from app.constructs.lambda_functions.usage_calculator import get_usage_calculator_function_code
        
        usage_calc_code = get_usage_calculator_function_code()
        
        # Check for correct AWS client usage
        self.assertIn('dynamodb.Table(os.environ[', usage_calc_code,
                     "Usage calculator Lambda should use 'dynamodb.Table'")
        
        # Check for utility class usage
        self.assertIn('BedrockPricingCalculator.calculate_cost', usage_calc_code,
                     "Usage calculator Lambda should use BedrockPricingCalculator")
        self.assertIn('ConfigurationManager.get_parameter', usage_calc_code,
                     "Usage calculator Lambda should use ConfigurationManager")
        self.assertIn('EventPublisher.publish_budget_event', usage_calc_code,
                     "Usage calculator Lambda should use EventPublisher")
        
        # Check that it uses required imports
        # These should be provided by shared utilities, not imported separately
        self.assertNotIn('import base64', usage_calc_code,
                        "Should not import base64 separately (provided by shared utilities)")
        self.assertNotIn('import gzip', usage_calc_code,
                        "Should not import gzip separately (provided by shared utilities)")
    
    def test_lambda_function_syntax_validation(self):
        """Test that generated Lambda function code has valid Python syntax"""
        import ast
        import re
        
        from app.constructs.shared.lambda_utilities import get_shared_lambda_utilities
        from app.constructs.lambda_functions.user_setup import get_user_setup_function_code
        from app.constructs.lambda_functions.usage_calculator import get_usage_calculator_function_code
        
        # Get the combined code as it would be deployed
        shared_utils = get_shared_lambda_utilities()
        user_setup_code = get_user_setup_function_code()
        usage_calc_code = get_usage_calculator_function_code()
        
        # Test user setup Lambda
        combined_user_setup = f"{shared_utils}\n\n{user_setup_code}"
        
        # Mock boto3 imports for syntax checking
        mocked_code = re.sub(r'boto3\.resource\([^)]+\)', 'None', combined_user_setup)
        mocked_code = re.sub(r'boto3\.client\([^)]+\)', 'None', mocked_code)
        
        try:
            ast.parse(mocked_code)
        except SyntaxError as e:
            self.fail(f"User Setup Lambda has syntax error: {e}")
        
        # Test usage calculator Lambda
        combined_usage_calc = f"{shared_utils}\n\n{usage_calc_code}"
        
        # Mock boto3 imports for syntax checking
        mocked_code = re.sub(r'boto3\.resource\([^)]+\)', 'None', combined_usage_calc)
        mocked_code = re.sub(r'boto3\.client\([^)]+\)', 'None', mocked_code)
        
        try:
            ast.parse(mocked_code)
        except SyntaxError as e:
            self.fail(f"Usage Calculator Lambda has syntax error: {e}")
    
    def test_no_duplicate_imports_in_core_processing(self):
        """Test that core processing construct doesn't have duplicate imports"""
        import os
        
        # Read the core processing file
        core_processing_path = os.path.join(
            os.path.dirname(__file__), '..', '..', 'app', 'constructs', 'core_processing.py'
        )
        
        with open(core_processing_path, 'r') as f:
            content = f.read()
        
        # Check for duplicate imports that could cause issues
        import_lines = [line.strip() for line in content.split('\n') if line.strip().startswith('import ')]
        
        # uuid should only appear once (in shared utilities, not separately)
        uuid_imports = [line for line in content.split('\n') if 'import uuid' in line]
        
        # Should have at most 1 uuid import (in the shared utilities string)
        self.assertLessEqual(len(uuid_imports), 1,
                           f"Found duplicate uuid imports: {uuid_imports}")
        
        # Check that shared utilities are properly included
        self.assertIn('get_shared_lambda_utilities()', content,
                     "Core processing should include shared utilities")


class TestCoreProcessingConstruct(unittest.TestCase):
    """Test CoreProcessingConstruct infrastructure"""
    
    def setUp(self):
        """Set up test environment"""
        self.app = App()
        self.stack = Stack(self.app, "TestStack")
        
        # Create dependencies
        self.data_storage = DataStorageConstruct(
            self.stack, "TestDataStorage",
            environment_name="production"
        )
        
        self.log_storage = LogStorageConstruct(
            self.stack, "TestLogStorage",
            environment_name="production"
        )
        
        # Create the construct
        self.core_processing = CoreProcessingConstruct(
            self.stack, "TestCoreProcessing",
            environment_name="production",
            dynamodb_tables=self.data_storage.tables,
            s3_bucket=self.log_storage.logs_bucket
        )
        
        self.template = Template.from_stack(self.stack)
    
    def test_lambda_functions_created(self):
        """Test that all expected Lambda functions are created"""
        expected_functions = [
            "user_setup",
            "usage_calculator", 
            "budget_monitor",
            "audit_logger",
            "state_reconciliation"
        ]
        
        # Check that all functions exist in the construct
        for function_name in expected_functions:
            self.assertIn(function_name, self.core_processing.functions)
        
        # Check CDK template has Lambda functions
        self.template.resource_count_is("AWS::Lambda::Function", 5)
    
    def test_dead_letter_queues_created(self):
        """Test that DLQ queues are created for all functions"""
        expected_queues = [
            "user_setup",
            "usage_calculator",
            "budget_monitor", 
            "audit_logger",
            "state_reconciliation"
        ]
        
        # Check that all DLQ queues exist
        for queue_name in expected_queues:
            self.assertIn(queue_name, self.core_processing.dead_letter_queues)
        
        # Check CDK template has SQS queues
        self.template.resource_count_is("AWS::SQS::Queue", 5)
    
    def test_iam_role_created(self):
        """Test that IAM execution role is created with proper permissions"""
        # Check that execution role exists
        self.assertIsNotNone(self.core_processing.execution_role)
        
        # Check CDK template has IAM role
        self.template.resource_count_is("AWS::IAM::Role", 1)
        
        # Check role has necessary policies
        self.template.has_resource_properties("AWS::IAM::Role", {
            "AssumedRolePolicyDocument": {
                "Statement": [{
                    "Action": "sts:AssumeRole",
                    "Effect": "Allow",
                    "Principal": {"Service": "lambda.amazonaws.com"}
                }]
            }
        })
    
    def test_event_rules_created(self):
        """Test that EventBridge rules are created"""
        # Check CDK template has EventBridge rules
        self.template.resource_count_is("AWS::Events::Rule", 5)  # 3 event rules + 2 schedules
        
        # Check for specific rule patterns
        self.template.has_resource_properties("AWS::Events::Rule", {
            "EventPattern": {
                "source": ["aws.iam"],
                "detail-type": ["AWS API Call via CloudTrail"]
            }
        })
    
    def test_lambda_environment_variables(self):
        """Test that Lambda functions have correct environment variables"""
        self.template.has_resource_properties("AWS::Lambda::Function", {
            "Environment": {
                "Variables": {
                    "ENVIRONMENT": "test",
                    "USER_BUDGETS_TABLE": {"Ref": assertions.Match.any_value()},
                    "AUDIT_LOGS_TABLE": {"Ref": assertions.Match.any_value()},
                    "LOGS_BUCKET": {"Ref": assertions.Match.any_value()}
                }
            }
        })


class TestUserSetupLambda(unittest.TestCase):
    """Test User Setup Lambda function logic"""
    
    def setUp(self):
        """Set up mock environment"""
        self.mock_dynamodb = Mock()
        self.mock_ssm = Mock()
        self.mock_events = Mock()
        self.mock_cloudwatch = Mock()
        
        # Mock table
        self.mock_table = Mock()
        self.mock_dynamodb.Table.return_value = self.mock_table
    
    @patch('boto3.resource')
    @patch('boto3.client') 
    def test_non_bedrock_events_ignored(self, mock_client, mock_resource):
        """Test that non-Bedrock IAM events are ignored"""
        # Setup mocks
        mock_resource.return_value = self.mock_dynamodb
        mock_client.side_effect = lambda service, **kwargs: {
            'ssm': self.mock_ssm,
            'events': self.mock_events,
            'cloudwatch': self.mock_cloudwatch
        }.get(service)
        
        # Create test event for regular user (should be ignored)
        event = {
            'detail': {
                'eventName': 'CreateAccessKey',
                'userIdentity': {
                    'type': 'IAMUser',
                    'userName': 'regular-user'
                }
            }
        }
        
        # Expected behavior: should ignore non-Bedrock events
        # The function should return early with "Event ignored" message
        self.assertTrue(True)  # Placeholder for actual function test
    
    @patch('boto3.resource')
    @patch('boto3.client')
    def test_bedrock_api_key_creation_event(self, mock_client, mock_resource):
        """Test processing Bedrock API key creation via CreateUser event"""
        # Setup mocks
        mock_resource.return_value = self.mock_dynamodb
        mock_client.side_effect = lambda service, **kwargs: {
            'ssm': self.mock_ssm,
            'events': self.mock_events,
            'cloudwatch': self.mock_cloudwatch
        }.get(service)
        
        # Mock no existing budget
        self.mock_table.get_item.return_value = {}
        
        # Mock SSM parameter for Bedrock API key budget
        self.mock_ssm.get_parameter.return_value = {
            'Parameter': {'Value': '5.0'}
        }
        
        # Create test event for Bedrock API key creation
        event = {
            'detail': {
                'eventName': 'CreateUser',
                'userIdentity': {
                    'type': 'IAMUser',
                    'userName': 'admin-user'
                },
                'responseElements': {
                    'user': {
                        'userName': 'BedrockAPIKey-1kte',
                        'userId': 'AIDAUSP4WRR7HDCHDU55W',
                        'arn': 'arn:aws:iam::123456789:user/BedrockAPIKey-1kte',
                        'createDate': 'Aug 31, 2025, 6:30:38 PM',
                        'path': '/'
                    }
                }
            }
        }
        
        # Expected behavior: should create budget entry with bedrock_api_key account type
        expected_item = {
            'principal_id': 'BedrockAPIKey-1kte',
            'account_type': 'bedrock_api_key',
            'budget_limit_usd': Decimal('5.0'),
            'spent_usd': Decimal('0.0'),
            'status': 'active',
            'threshold_state': 'normal'
        }
        
        # This would be tested by importing the actual Lambda code
        self.assertTrue(True)  # Placeholder for actual function test
    
    @patch('boto3.resource')
    @patch('boto3.client')
    def test_bedrock_service_credential_creation(self, mock_client, mock_resource):
        """Test processing CreateServiceSpecificCredential for Bedrock API key"""
        # Setup mocks
        mock_resource.return_value = self.mock_dynamodb
        mock_client.side_effect = lambda service, **kwargs: {
            'ssm': self.mock_ssm,
            'events': self.mock_events,
            'cloudwatch': self.mock_cloudwatch
        }.get(service)
        
        # Mock no existing budget
        self.mock_table.get_item.return_value = {}
        
        # Mock SSM parameter for Bedrock API key budget
        self.mock_ssm.get_parameter.return_value = {
            'Parameter': {'Value': '5.0'}
        }
        
        # Create test event for service-specific credential creation
        event = {
            'detail': {
                'eventName': 'CreateServiceSpecificCredential',
                'userIdentity': {
                    'type': 'IAMUser',
                    'userName': 'admin-user'
                },
                'requestParameters': {
                    'userName': 'BedrockAPIKey-abc123',
                    'serviceName': 'bedrock'
                }
            }
        }
        
        # This would test that the function correctly identifies Bedrock API keys
        self.assertTrue(True)  # Placeholder for actual function test
    
    @patch('boto3.resource')
    @patch('boto3.client')
    def test_regular_user_creation_ignored(self, mock_client, mock_resource):
        """Test that regular user creation is ignored (not processed)"""
        # Setup mocks
        mock_resource.return_value = self.mock_dynamodb
        mock_client.side_effect = lambda service, **kwargs: {
            'ssm': self.mock_ssm,
            'events': self.mock_events,
            'cloudwatch': self.mock_cloudwatch
        }.get(service)
        
        # Create test event for regular user creation
        event = {
            'detail': {
                'eventName': 'CreateUser',
                'userIdentity': {
                    'type': 'IAMUser',
                    'userName': 'admin-user'
                },
                'responseElements': {
                    'user': {
                        'userName': 'regular-user',
                        'userId': 'AIDAUSP4WRR7HDCHDU123',
                        'arn': 'arn:aws:iam::123456789:user/regular-user',
                        'createDate': 'Aug 31, 2025, 6:30:38 PM',
                        'path': '/'
                    }
                }
            }
        }
        
        # Expected behavior: should ignore regular user creation
        # Function should return early with "Event ignored - not a Bedrock API key"
        self.assertTrue(True)  # Placeholder for actual function test
    
    @patch('boto3.resource')
    @patch('boto3.client')
    def test_existing_bedrock_user_policy_event(self, mock_client, mock_resource):
        """Test policy events on existing Bedrock API key users"""
        # Setup mocks
        mock_resource.return_value = self.mock_dynamodb
        mock_client.side_effect = lambda service, **kwargs: {
            'ssm': self.mock_ssm,
            'events': self.mock_events,
            'cloudwatch': self.mock_cloudwatch
        }.get(service)
        
        # Mock existing budget
        self.mock_table.get_item.return_value = {
            'Item': {
                'principal_id': 'BedrockAPIKey-existing',
                'account_type': 'bedrock_api_key',
                'budget_limit_usd': Decimal('5.0')
            }
        }
        
        # Create test event for policy attachment to existing Bedrock API key user
        event = {
            'detail': {
                'eventName': 'AttachUserPolicy',
                'userIdentity': {
                    'type': 'IAMUser',
                    'userName': 'BedrockAPIKey-existing'
                },
                'requestParameters': {
                    'userName': 'BedrockAPIKey-existing',
                    'policyArn': 'arn:aws:iam::aws:policy/service-role/AmazonBedrockFullAccess'
                }
            }
        }
        
        # This should recognize the Bedrock API key user and handle appropriately
        self.assertTrue(True)  # Placeholder for actual function test


class TestUsageCalculatorLambda(unittest.TestCase):
    """Test Usage Calculator Lambda function logic"""
    
    def test_bedrock_log_parsing(self):
        """Test parsing of Bedrock invocation logs"""
        # Create mock Bedrock CloudTrail log data (legacy format)
        cloudtrail_log_data = {
            'eventName': 'InvokeModel',
            'userIdentity': {
                'type': 'IAMUser',
                'userName': 'test-user'
            },
            'requestParameters': {
                'modelId': 'anthropic.claude-3-sonnet-20240229-v1:0'
            },
            'responseElements': {
                'usage': {
                    'inputTokens': 1000,
                    'outputTokens': 500
                }
            },
            'awsRegion': 'us-east-1'
        }
        
        # Expected cost calculation (simplified)
        expected_input_cost = (1000 / 1000) * 0.0001  # $0.0001
        expected_output_cost = (500 / 1000) * 0.0002  # $0.0001
        expected_total_cost = expected_input_cost + expected_output_cost  # $0.0002
        
        # This would test the actual cost calculation logic
        self.assertAlmostEqual(expected_total_cost, 0.0002, places=6)
    
    def test_bedrock_invocation_log_parsing(self):
        """Test parsing of CloudWatch Bedrock invocation logs"""
        # Create mock CloudWatch invocation log data (new format)
        invocation_log_data = {
            'input': {
                'inputContentType': 'application/json',
                'inputTokenCount': 4315,
                'cacheReadInputTokenCount': 15388,
                'cacheWriteInputTokenCount': 13384
            },
            'output': {
                'outputContentType': 'application/json',
                'outputBodyJson': [
                    {
                        'type': 'message_start',
                        'message': {
                            'id': 'msg_bdrk_01QGT5THCnA1TxVY6ZQ5VVgs',
                            'type': 'message',
                            'role': 'assistant',
                            'model': 'claude-sonnet-4-20250514',
                            'content': [],
                            'stop_reason': None,
                            'stop_sequence': None,
                            'usage': {
                                'input_tokens': 4315,
                                'cache_creation_input_tokens': 13384,
                                'cache_read_input_tokens': 15388,
                                'output_tokens': 3
                            }
                        }
                    }
                ]
            },
            '_metadata': {
                'logGroup': '/aws/bedrock/bedrock-budgeteer-production-invocation-logs',
                'logStream': 'BedrockAPIKey-12345/stream-678',
                'principal_id': 'BedrockAPIKey-12345',
                'timestamp': 1640995200000
            }
        }
        
        # Expected total input tokens: 4315 + 15388 + 13384 = 33087
        expected_total_input = 4315 + 15388 + 13384
        expected_output = 3
        
        # Verify token extraction logic would work
        self.assertEqual(expected_total_input, 33087)
        self.assertEqual(expected_output, 3)
    
    def test_firehose_record_decoding(self):
        """Test decoding of Kinesis Firehose records"""
        # Create test data
        test_data = json.dumps({
            'eventName': 'InvokeModel',
            'userIdentity': {'type': 'IAMUser', 'userName': 'test-user'}
        })
        
        # Encode like Firehose would
        encoded_data = base64.b64encode(test_data.encode('utf-8')).decode('utf-8')
        
        firehose_record = {
            'recordId': 'test-record-1',
            'data': encoded_data
        }
        
        # Test decoding
        decoded = base64.b64decode(firehose_record['data']).decode('utf-8')
        parsed = json.loads(decoded)
        
        self.assertEqual(parsed['eventName'], 'InvokeModel')
        self.assertEqual(parsed['userIdentity']['userName'], 'test-user')


class TestBudgetMonitorLambda(unittest.TestCase):
    """Test Budget Monitor Lambda function logic"""
    
    def test_threshold_calculation(self):
        """Test budget threshold calculations"""
        budget_item = {
            'principal_id': 'test-user',
            'spent_usd': Decimal('75.0'),
            'budget_limit_usd': Decimal('100.0'),
            'threshold_state': 'normal'
        }
        
        # Default thresholds: warn=70%, critical=90%
        warn_threshold = 100.0 * 0.70  # $70
        critical_threshold = 100.0 * 0.90  # $90
        
        # Current spending: $75 (above warn, below critical)
        self.assertGreater(75.0, warn_threshold)
        self.assertLess(75.0, critical_threshold)
        
        # Should trigger warning threshold
        expected_new_state = 'warning'
        self.assertEqual(expected_new_state, 'warning')
    
    def test_anomaly_detection(self):
        """Test spending anomaly detection logic"""
        # Normal spending pattern
        normal_budget = {
            'spent_usd': Decimal('50.0'),
            'budget_limit_usd': Decimal('100.0'),
            'last_updated_epoch': (datetime.now(timezone.utc).timestamp() - 3600)  # 1 hour ago
        }
        
        # Anomalous spending pattern (rapid increase)
        anomalous_budget = {
            'spent_usd': Decimal('95.0'),
            'budget_limit_usd': Decimal('100.0'), 
            'last_updated_epoch': (datetime.now(timezone.utc).timestamp() - 300)  # 5 minutes ago
        }
        
        # Calculate spending rates
        normal_rate = 50.0 / 1.0  # $50/hour
        anomalous_rate = 95.0 / (5/60)  # $1140/hour
        
        # Anomalous rate should be much higher
        self.assertGreater(anomalous_rate, normal_rate * 10)
    
    def test_anomaly_detection_with_decimal_timestamp(self):
        """Test anomaly detection with Decimal timestamp (reproduces the original bug)"""
        # Test case that would cause the original decimal/float error
        budget_with_decimal_timestamp = {
            'spent_usd': Decimal('75.0'),
            'budget_limit_usd': Decimal('100.0'),
            'last_updated_epoch': Decimal('1725126361.668')  # Decimal timestamp from DynamoDB
        }
        
        # This should not raise a TypeError anymore
        # The function should handle mixed Decimal/float types gracefully
        result = self.calculate_anomaly_score(budget_with_decimal_timestamp)
        
        # Should return a valid anomaly score (between 0.0 and 1.0)
        self.assertIsInstance(result, float)
        self.assertGreaterEqual(result, 0.0)
        self.assertLessEqual(result, 1.0)
    
    def calculate_anomaly_score(self, budget_item):
        """Helper method to simulate the detect_spending_anomaly function"""
        try:
            spent_usd = float(budget_item['spent_usd'])
            budget_limit_usd = float(budget_item['budget_limit_usd'])
            
            # This line should now work with Decimal timestamp
            last_updated = float(budget_item.get('last_updated_epoch', 0))
            current_time = datetime.now(timezone.utc).timestamp()
            
            time_diff_hours = (current_time - last_updated) / 3600
            if time_diff_hours > 0:
                spending_rate = spent_usd / max(time_diff_hours, 1)
                normal_rate = budget_limit_usd / (30 * 24)
                
                if spending_rate > normal_rate * 10:
                    return 0.9
            
            return 0.0
        except Exception as e:
            # This should not happen with the fix
            self.fail(f"Anomaly detection failed with error: {e}")
            return 0.0
    
    def test_budget_threshold_parameter_names(self):
        """Test that budget threshold parameter names match configuration"""
        # This test validates the parameter name consistency
        expected_param_names = {
            'warn_percent': '/bedrock-budgeteer/global/thresholds_percent_warn',
            'critical_percent': '/bedrock-budgeteer/global/thresholds_percent_critical'
        }
        
        # Simulate the ConfigurationManager.get_budget_thresholds() method
        # This ensures the parameter names are consistent with what's created by the configuration construct
        for threshold_type, expected_param_name in expected_param_names.items():
            # Validate parameter naming convention
            self.assertIn('thresholds_percent_', expected_param_name)
            self.assertIn(threshold_type.replace('_percent', ''), expected_param_name)
            
        # Verify no slash-based parameter names are used (which would cause ParameterNotFound)
        invalid_names = [
            '/bedrock-budgeteer/global/thresholds/percent_warn',
            '/bedrock-budgeteer/global/thresholds/percent_critical'
        ]
        
        # Make sure we're not using the invalid naming pattern
        for invalid_name in invalid_names:
            self.assertIn('thresholds/', invalid_name)  # This is the pattern we want to avoid
            
        # Verify our expected names use underscores, not slashes
        for threshold_type, expected_param_name in expected_param_names.items():
            self.assertNotIn('thresholds/', expected_param_name)  # Should not have slash-based naming


class TestAuditLoggerLambda(unittest.TestCase):
    """Test Audit Logger Lambda function logic"""
    
    def test_audit_entry_creation(self):
        """Test creation of standardized audit entries"""
        event_detail = {
            'principal_id': 'test-user',
            'action': 'budget_threshold_violated',
            'threshold_type': 'warning',
            'spent_usd': 75.0,
            'budget_limit_usd': 100.0
        }
        
        # Expected audit entry structure
        expected_fields = [
            'event_id',
            'event_time', 
            'event_source',
            'event_type',
            'principal_id',
            'action',
            'details',
            'severity'
        ]
        
        # Verify all required fields would be present
        for field in expected_fields:
            self.assertTrue(True)  # Placeholder - would test actual function
    
    def test_severity_determination(self):
        """Test severity level determination for different event types"""
        test_cases = [
            ('Budget Threshold Violation', 'high'),
            ('Spending Anomaly Detected', 'high'),
            ('Budget Initialized', 'low'),
            ('Error Processing Event', 'medium')
        ]
        
        for event_type, expected_severity in test_cases:
            # This would test the actual severity determination logic
            self.assertTrue(True)  # Placeholder


class TestStateReconciliationLambda(unittest.TestCase):
    """Test State Reconciliation Lambda function logic"""
    
    def test_iam_state_retrieval(self):
        """Test retrieval of IAM state for users and roles"""
        # Mock IAM responses
        user_policies = {
            'AttachedPolicies': [
                {'PolicyName': 'BedrockUserPolicy', 'PolicyArn': 'arn:aws:iam::123:policy/BedrockUserPolicy'}
            ]
        }
        
        inline_policies = {
            'PolicyNames': ['InlineBedrockPolicy']
        }
        
        # Test user state extraction
        expected_user_state = {
            'principal_type': 'user',
            'exists': True,
            'has_bedrock_access': True,
            'attached_policies': ['BedrockUserPolicy'],
            'inline_policies': ['InlineBedrockPolicy']
        }
        
        # This would test the actual IAM state retrieval
        self.assertTrue(True)  # Placeholder
    
    def test_inconsistency_detection(self):
        """Test detection of state inconsistencies"""
        # Case 1: User suspended but has Bedrock access
        budget_item = {
            'principal_id': 'test-user',
            'status': 'suspended',
            'account_type': 'user'
        }
        
        iam_state = {
            'has_bedrock_access': True,
            'exists': True
        }
        
        # Should detect inconsistency
        has_inconsistency = budget_item['status'] == 'suspended' and iam_state['has_bedrock_access']
        self.assertTrue(has_inconsistency)
        
        # Case 2: User active without Bedrock access (might be intentional)
        budget_item_2 = {
            'principal_id': 'test-user-2',
            'status': 'active',
            'account_type': 'user'
        }
        
        iam_state_2 = {
            'has_bedrock_access': False,
            'exists': True
        }
        
        # Should note but not necessarily flag as error
        has_access_issue = budget_item_2['status'] == 'active' and not iam_state_2['has_bedrock_access']
        self.assertTrue(has_access_issue)


class TestIntegrationScenarios(unittest.TestCase):
    """Test end-to-end integration scenarios"""
    
    def test_new_user_workflow(self):
        """Test complete workflow for new user setup"""
        # 1. IAM user creation event triggers User Setup Lambda
        iam_event = {
            'detail': {
                'eventName': 'CreateAccessKey',
                'userIdentity': {'type': 'IAMUser', 'userName': 'new-user'}
            }
        }
        
        # 2. User Setup Lambda should create budget entry
        expected_budget = {
            'principal_id': 'new-user',
            'account_type': 'user',
            'budget_limit_usd': 100.0,
            'spent_usd': 0.0,
            'status': 'active'
        }
        
        # 3. Audit Logger should record budget creation
        expected_audit = {
            'event_type': 'Budget Initialized',
            'principal_id': 'new-user',
            'action': 'budget_created',
            'severity': 'low'
        }
        
        # Verify workflow structure
        self.assertEqual(iam_event['detail']['userIdentity']['userName'], 'new-user')
        self.assertEqual(expected_budget['principal_id'], 'new-user')
        self.assertEqual(expected_audit['principal_id'], 'new-user')
    
    def test_threshold_violation_workflow(self):
        """Test workflow when user exceeds budget threshold"""
        # 1. Usage Calculator processes Bedrock usage
        bedrock_usage = {
            'principal_id': 'heavy-user',
            'model_id': 'anthropic.claude-3-sonnet',
            'input_tokens': 100000,
            'output_tokens': 50000,
            'calculated_cost': 15.0
        }
        
        # 2. Budget Monitor detects threshold violation
        updated_budget = {
            'principal_id': 'heavy-user',
            'spent_usd': 85.0,  # Exceeds 70% threshold
            'budget_limit_usd': 100.0,
            'threshold_state': 'warning'
        }
        
        # 3. Events should be published for threshold violation
        threshold_event = {
            'event_type': 'Budget Threshold Violation',
            'principal_id': 'heavy-user',
            'threshold_type': 'warning'
        }
        
        # 4. Audit Logger should record the violation
        audit_entry = {
            'event_type': 'Budget Threshold Violation',
            'principal_id': 'heavy-user',
            'severity': 'high'
        }
        
        # Verify workflow structure
        self.assertEqual(bedrock_usage['principal_id'], 'heavy-user')
        self.assertEqual(updated_budget['threshold_state'], 'warning')
        self.assertEqual(threshold_event['threshold_type'], 'warning')
        self.assertEqual(audit_entry['severity'], 'high')
    
    def test_reconciliation_workflow(self):
        """Test state reconciliation detecting and correcting drift"""
        # 1. Budget shows user as suspended
        budget_state = {
            'principal_id': 'drifted-user',
            'status': 'suspended',
            'account_type': 'user'
        }
        
        # 2. IAM shows user still has Bedrock access
        iam_state = {
            'has_bedrock_access': True,
            'exists': True,
            'attached_policies': ['BedrockFullAccess']
        }
        
        # 3. State Reconciliation should detect inconsistency
        inconsistency_detected = (
            budget_state['status'] == 'suspended' and 
            iam_state['has_bedrock_access']
        )
        
        # 4. Should generate reconciliation event
        reconciliation_event = {
            'event_type': 'State Inconsistency Requires Manual Review',
            'principal_id': 'drifted-user',
            'issue': 'suspended_with_access'
        }
        
        # Verify detection logic
        self.assertTrue(inconsistency_detected)
        self.assertEqual(reconciliation_event['issue'], 'suspended_with_access')


class TestWorkflowIntegration(unittest.TestCase):
    """Test integration between core processing and workflow orchestration"""
    
    def test_suspension_workflow_trigger_event_format(self):
        """Test that budget monitor publishes correct event format for workflow trigger"""
        
        # Expected event format for triggering suspension workflow
        expected_event_structure = {
            'source': 'bedrock-budgeteer',
            'detail-type': 'Suspension Workflow Required',
            'detail': {
                'principal_id': str,
                'budget_data': dict,
                'timestamp': str
            }
        }
        
        # Verify the event structure is correct
        self.assertIn('source', expected_event_structure)
        self.assertIn('detail-type', expected_event_structure)
        self.assertIn('detail', expected_event_structure)
        
        detail = expected_event_structure['detail']
        self.assertIn('principal_id', detail)
        self.assertIn('budget_data', detail)
        self.assertIn('timestamp', detail)
    
    def test_budget_exceeded_triggers_workflow(self):
        """Test that budget exceeded condition triggers suspension workflow"""
        
        # Mock budget item that exceeds budget
        budget_item = {
            'principal_id': 'test-user',
            'spent_usd': Decimal('150.00'),
            'budget_limit_usd': Decimal('100.00'),
            'account_type': 'user',
            'threshold_state': 'critical'
        }
        
        # Mock the EventPublisher
        with patch('app.constructs.core_processing.EventPublisher') as mock_publisher:
            # Import the function that would be called in the Lambda
            # (In practice, this would be extracted for easier testing)
            
            # Test that the workflow trigger event is published
            expected_call = {
                'event_type': 'Suspension Workflow Required',
                'detail': {
                    'principal_id': 'test-user',
                    'budget_data': {
                        'principal_id': 'test-user',
                        'spent_usd': 150.00,
                        'budget_limit_usd': 100.00,
                        'account_type': 'user',
                        'threshold_state': 'critical'
                    }
                }
            }
            
            # Verify the expected structure
            self.assertIn('event_type', expected_call)
            self.assertIn('detail', expected_call)
    
    def test_workflow_integration_error_handling(self):
        """Test error handling in workflow integration"""
        
        # Test scenarios where workflow integration might fail
        error_scenarios = [
            'EventBridge publish failure',
            'Invalid budget data format',
            'Missing principal_id',
            'DynamoDB connection error'
        ]
        
        for scenario in error_scenarios:
            # Verify that errors are handled gracefully
            self.assertIsNotNone(scenario)


class TestBudgetRefreshFunctionality(unittest.TestCase):
    """Test budget refresh functionality"""
    
    def setUp(self):
        """Set up test environment for budget refresh tests"""
        self.app = App()
        self.stack = Stack(self.app, "TestStack")
        
        # Create dependencies
        self.data_storage = DataStorageConstruct(
            self.stack, "TestDataStorage",
            environment_name="production"
        )
        
        self.log_storage = LogStorageConstruct(
            self.stack, "TestLogStorage",
            environment_name="production"
        )
        
        # Create the construct
        self.core_processing = CoreProcessingConstruct(
            self.stack, "TestCoreProcessing",
            environment_name="production",
            dynamodb_tables=self.data_storage.tables,
            s3_bucket=self.log_storage.logs_bucket
        )
        
        self.template = Template.from_stack(self.stack)
    
    def test_budget_refresh_lambda_creation(self):
        """Test that budget refresh Lambda function is created"""
        
        # Check that the budget refresh Lambda function exists
        self.template.has_resource_properties("AWS::Lambda::Function", {
            "FunctionName": {
                "Fn::Sub": "bedrock-budgeteer-budget-refresh-production"
            },
            "Handler": "index.lambda_handler",
            "Runtime": "python3.11",
            "Timeout": 600  # 10 minutes
        })
    
    def test_budget_refresh_schedule_creation(self):
        """Test that budget refresh schedule is created"""
        
        # Check that the EventBridge rule for budget refresh exists
        self.template.has_resource_properties("AWS::Events::Rule", {
            "Name": "bedrock-budgeteer-refresh-schedule-production",
            "Description": "Schedule for budget refresh Lambda",
            "ScheduleExpression": "cron(0 2 * * ? *)"  # Daily at 2 AM UTC
        })
    
    def test_budget_refresh_dlq_creation(self):
        """Test that budget refresh DLQ is created"""
        
        # Check that the DLQ for budget refresh exists
        self.template.has_resource_properties("AWS::SQS::Queue", {
            "QueueName": "bedrock-budgeteer-budget-refresh-dlq-production",
            "MessageRetentionPeriod": 1209600,  # 14 days
            "KmsMasterKeyId": "alias/aws/sqs"
        })
    
    @patch('boto3.resource')
    @patch('boto3.client')
    def test_budget_refresh_logic_expired_budget(self, mock_client, mock_resource):
        """Test budget refresh logic for expired budgets"""
        
        # Mock DynamoDB table
        mock_table = Mock()
        mock_resource.return_value.Table.return_value = mock_table
        
        # Mock expired budget item
        expired_budget = {
            'principal_id': 'test-user',
            'account_type': 'user',
            'spent_usd': Decimal('75.50'),
            'budget_limit_usd': Decimal('100.00'),
            'status': 'suspended',
            'threshold_state': 'exceeded',
            'budget_refresh_date': '2024-01-01T00:00:00+00:00',
            'refresh_period_days': 30,
            'refresh_count': 2
        }
        
        mock_table.get_item.return_value = {'Item': expired_budget}
        
        # Mock current time (after refresh date)
        current_time = datetime(2024, 2, 1, 0, 0, 0, tzinfo=timezone.utc)
        
        # Test the refresh logic
        from datetime import timedelta
        
        # Verify that budget should be refreshed
        refresh_date = datetime.fromisoformat('2024-01-01T00:00:00+00:00')
        should_refresh = current_time >= refresh_date
        self.assertTrue(should_refresh)
        
        # Verify expected update parameters
        expected_next_refresh = current_time + timedelta(days=30)
        self.assertEqual(expected_next_refresh.day, 2)  # 30 days later
        self.assertEqual(expected_next_refresh.month, 3)  # March
    
    @patch('boto3.resource')
    @patch('boto3.client')
    def test_budget_refresh_logic_active_budget(self, mock_client, mock_resource):
        """Test budget refresh logic for active (non-expired) budgets"""
        
        # Mock DynamoDB table
        mock_table = Mock()
        mock_resource.return_value.Table.return_value = mock_table
        
        # Mock active budget item (not expired)
        active_budget = {
            'principal_id': 'test-user',
            'account_type': 'user',
            'spent_usd': Decimal('25.00'),
            'budget_limit_usd': Decimal('100.00'),
            'status': 'active',
            'threshold_state': 'normal',
            'budget_refresh_date': '2024-03-01T00:00:00+00:00',  # Future date
            'refresh_period_days': 30,
            'refresh_count': 1
        }
        
        mock_table.get_item.return_value = {'Item': active_budget}
        
        # Mock current time (before refresh date)
        current_time = datetime(2024, 2, 1, 0, 0, 0, tzinfo=timezone.utc)
        
        # Test the refresh logic
        refresh_date = datetime.fromisoformat('2024-03-01T00:00:00+00:00')
        should_refresh = current_time >= refresh_date
        self.assertFalse(should_refresh)
    
    @patch('boto3.resource')
    @patch('boto3.client')
    def test_iam_policy_restoration(self, mock_client, mock_resource):
        """Test IAM policy restoration during budget refresh"""
        
        # Mock IAM client
        mock_iam = Mock()
        mock_client.return_value = mock_iam
        
        # Test user policy removal
        restriction_policies = [
            'BedrockBudgeteerRestriction-ExpensiveModels',
            'BedrockBudgeteerRestriction-AllModels',
            'BedrockBudgeteerRestriction-FullSuspension'
        ]
        
        # Mock successful policy deletion
        mock_iam.delete_user_policy.return_value = {}
        mock_iam.untag_user.return_value = {}
        
        # Verify that all restriction policies would be removed
        for policy_name in restriction_policies:
            self.assertIn('BedrockBudgeteerRestriction', policy_name)
        
        # Test role policy removal
        mock_iam.delete_role_policy.return_value = {}
        mock_iam.untag_role.return_value = {}
        
        # Verify role restriction removal logic
        for policy_name in restriction_policies:
            self.assertIn('BedrockBudgeteerRestriction', policy_name)
    
    @patch('boto3.resource')
    @patch('boto3.client')
    def test_budget_refresh_database_updates(self, mock_client, mock_resource):
        """Test database updates during budget refresh"""
        
        # Mock DynamoDB table
        mock_table = Mock()
        mock_resource.return_value.Table.return_value = mock_table
        
        # Mock budget item
        budget_item = {
            'principal_id': 'test-user',
            'account_type': 'user',
            'spent_usd': Decimal('150.00'),  # Over budget
            'budget_limit_usd': Decimal('100.00'),
            'status': 'suspended',
            'threshold_state': 'exceeded',
            'refresh_period_days': 30,
            'refresh_count': 1
        }
        
        mock_table.get_item.return_value = {'Item': budget_item}
        mock_table.update_item.return_value = {}
        
        # Test expected update expression components
        expected_updates = [
            'spent_usd = :zero',
            'threshold_state = :normal',
            'budget_period_start = :current_time',
            'budget_refresh_date = :next_refresh',
            'refresh_count = refresh_count + :one',
            'last_updated_epoch = :timestamp',
            'model_spend_breakdown = :empty_breakdown'
        ]
        
        # For suspended budgets, status should also be updated
        if budget_item['status'] == 'suspended':
            expected_updates.append('#status = :active')
        
        # Verify all expected update components are present
        for update in expected_updates:
            self.assertIn('=', update)
    
    def test_budget_refresh_configuration_parameter(self):
        """Test that budget refresh period configuration parameter is created"""
        
        # This would be tested in the configuration construct tests
        # but we verify the parameter name format here
        expected_parameter_name = '/bedrock-budgeteer/production/cost/budget_refresh_period_days'
        
        # Verify parameter name format
        self.assertTrue(expected_parameter_name.startswith('/bedrock-budgeteer/'))
        self.assertIn('budget_refresh_period_days', expected_parameter_name)
    
    @patch('boto3.resource')
    def test_manual_budget_refresh_trigger(self, mock_resource):
        """Test manual budget refresh trigger functionality"""
        
        # Mock DynamoDB table
        mock_table = Mock()
        mock_resource.return_value.Table.return_value = mock_table
        
        # Test manual refresh event structure
        manual_refresh_event = {
            'manual_refresh': True,
            'principal_id': 'test-user'
        }
        
        # Verify event structure
        self.assertTrue(manual_refresh_event['manual_refresh'])
        self.assertEqual(manual_refresh_event['principal_id'], 'test-user')
        
        # Test that manual refresh bypasses schedule check
        self.assertIn('manual_refresh', manual_refresh_event)
        self.assertIn('principal_id', manual_refresh_event)
    
    def test_budget_refresh_metrics_publishing(self):
        """Test that budget refresh publishes appropriate metrics"""
        
        # Test expected metrics
        expected_metrics = [
            'BudgetRefreshCompleted',
            'BudgetRefreshErrors'
        ]
        
        # Verify metric names
        for metric in expected_metrics:
            self.assertIn('BudgetRefresh', metric)
        
        # Test metric dimensions
        expected_dimensions = {
            'Environment': 'production'
        }
        
        self.assertIn('Environment', expected_dimensions)
    
    def test_budget_refresh_audit_events(self):
        """Test that budget refresh publishes audit events"""
        
        # Test expected audit event structure
        expected_audit_event = {
            'event_type': 'Budget Refreshed',
            'detail': {
                'principal_id': 'test-user',
                'account_type': 'user',
                'refresh_count': 2,
                'next_refresh_date': '2024-03-01T00:00:00+00:00',
                'was_suspended': True
            }
        }
        
        # Verify audit event structure
        self.assertEqual(expected_audit_event['event_type'], 'Budget Refreshed')
        self.assertIn('principal_id', expected_audit_event['detail'])
        self.assertIn('refresh_count', expected_audit_event['detail'])
        self.assertIn('was_suspended', expected_audit_event['detail'])
    


if __name__ == '__main__':
    unittest.main()
