"""
Integration tests for Event Ingestion & Storage
Tests the complete ingestion pipeline from CloudTrail to storage
"""

import unittest

import aws_cdk as cdk
from aws_cdk import assertions

from app.app_stack import BedrockBudgeteerStack


class TestIntegration(unittest.TestCase):
    """Test ingestion pipeline integration"""

    def setUp(self):
        """Set up test environment"""
        self.app = cdk.App()
        self.stack = BedrockBudgeteerStack(
            self.app, 
            "TestBedrockBudgeteerStack",
            environment_name="production"
        )
        self.template = assertions.Template.from_stack(self.stack)

    def test_dynamodb_tables_created(self):
        """Test that all required DynamoDB tables are created"""
        # Test user budgets table
        self.template.has_resource("AWS::DynamoDB::Table", {
            "Properties": {
                "TableName": "bedrock-budgeteer-production-user-budgets",
                "KeySchema": [
                    {
                        "AttributeName": "principal_id",
                        "KeyType": "HASH"
                    }
                ]
            }
        })
        
        # Test usage tracking table
        self.template.has_resource("AWS::DynamoDB::Table", {
            "Properties": {
                "TableName": "bedrock-budgeteer-production-usage-tracking",
                "KeySchema": [
                    {
                        "AttributeName": "principal_id",
                        "KeyType": "HASH"
                    },
                    {
                        "AttributeName": "timestamp",
                        "KeyType": "RANGE"
                    }
                ]
            }
        })
        
        # Test audit logs table
        self.template.has_resource("AWS::DynamoDB::Table", {
            "Properties": {
                "TableName": "bedrock-budgeteer-production-audit-logs",
                "KeySchema": [
                    {
                        "AttributeName": "event_id",
                        "KeyType": "HASH"
                    },
                    {
                        "AttributeName": "event_time",
                        "KeyType": "RANGE"
                    }
                ]
            }
        })

    def test_s3_buckets_created(self):
        """Test that S3 buckets are created with proper configuration"""
        # Test logs bucket
        self.template.has_resource("AWS::S3::Bucket", {
            "Properties": {
                "BucketName": "bedrock-budgeteer-production-logs",
                "BucketEncryption": {
                    "ServerSideEncryptionConfiguration": [
                        {
                            "ServerSideEncryptionByDefault": {
                                "SSEAlgorithm": "AES256"
                            }
                        }
                    ]
                }
            }
        })
        


    def test_cloudtrail_created(self):
        """Test that CloudTrail is created with proper configuration"""
        self.template.has_resource("AWS::CloudTrail::Trail", {
            "Properties": {
                "TrailName": "bedrock-budgeteer-production-trail",
                "IncludeGlobalServiceEvents": True,
                "IsMultiRegionTrail": True,
                "EnableLogFileValidation": True
            }
        })

    def test_eventbridge_rules_created(self):
        """Test that EventBridge rules are created"""
        # Test Bedrock usage rule
        self.template.has_resource("AWS::Events::Rule", {
            "Properties": {
                "Name": "bedrock-budgeteer-production-bedrock-usage",
                "EventPattern": {
                    "source": ["aws.bedrock"],
                    "detail-type": ["AWS API Call via CloudTrail"],
                    "detail": {
                        "eventSource": ["bedrock.amazonaws.com"],
                        "eventName": [
                            "InvokeModel",
                            "InvokeModelWithResponseStream",
                            "GetFoundationModel",
                            "ListFoundationModels"
                        ]
                    }
                }
            }
        })
        
        # Test IAM key creation rule
        self.template.has_resource("AWS::Events::Rule", {
            "Properties": {
                "Name": "bedrock-budgeteer-production-iam-key-creation",
                "EventPattern": {
                    "source": ["aws.iam"],
                    "detail-type": ["AWS API Call via CloudTrail"],
                    "detail": {
                        "eventSource": ["iam.amazonaws.com"],
                        "eventName": [
                            "CreateUser",
                            "CreateServiceSpecificCredential",
                            "AttachRolePolicy"
                        ]
                    }
                }
            }
        })

    def test_kinesis_firehose_streams_created(self):
        """Test that Kinesis Data Firehose streams are created"""
        # Test Bedrock usage firehose stream
        self.template.has_resource("AWS::KinesisFirehose::DeliveryStream", {
            "Properties": {
                "DeliveryStreamName": "bedrock-budgeteer-production-usage-logs",
                "DeliveryStreamType": "DirectPut"
            }
        })
        
        # Test audit logs firehose stream
        self.template.has_resource("AWS::KinesisFirehose::DeliveryStream", {
            "Properties": {
                "DeliveryStreamName": "bedrock-budgeteer-production-audit-logs",
                "DeliveryStreamType": "DirectPut"
            }
        })

    def test_cloudwatch_alarms_created(self):
        """Test that CloudWatch alarms are created for monitoring"""
        # Should have alarms for DynamoDB tables
        self.template.has_resource_properties("AWS::CloudWatch::Alarm", {
            "AlarmName": "bedrock-budgeteer-production-user_budgets-read-throttles",
            "MetricName": "UserErrors",
            "Namespace": "AWS/DynamoDB"
        })

    def test_sns_topics_created(self):
        """Test that SNS topics are created for notifications"""
        # Test operational alerts topic
        self.template.has_resource("AWS::SNS::Topic", {
            "Properties": {
                "TopicName": "bedrock-budgeteer-production-operational-alerts",
                "DisplayName": "Bedrock Budgeteer Operational Alerts"
            }
        })
        
        # Test budget alerts topic
        self.template.has_resource("AWS::SNS::Topic", {
            "Properties": {
                "TopicName": "bedrock-budgeteer-production-budget-alerts",
                "DisplayName": "Bedrock Budgeteer Budget Alerts"
            }
        })

    def test_gsi_created_for_tables(self):
        """Test that Global Secondary Indexes are created"""
        # User budgets table should have BudgetStatusIndex
        self.template.has_resource("AWS::DynamoDB::Table", {
            "Properties": {
                "TableName": "bedrock-budgeteer-production-user-budgets",
                "GlobalSecondaryIndexes": [
                    {
                        "IndexName": "BudgetStatusIndex",
                        "KeySchema": [
                            {
                                "AttributeName": "budget_status",
                                "KeyType": "HASH"
                            },
                            {
                                "AttributeName": "created_at",
                                "KeyType": "RANGE"
                            }
                        ]
                    }
                ]
            }
        })
        
        # Audit logs table should have UserAuditIndex and EventSourceIndex
        self.template.has_resource("AWS::DynamoDB::Table", {
            "Properties": {
                "TableName": "bedrock-budgeteer-production-audit-logs",
                "GlobalSecondaryIndexes": [
                    {
                        "IndexName": "UserAuditIndex",
                        "KeySchema": [
                            {
                                "AttributeName": "user_identity",
                                "KeyType": "HASH"
                            },
                            {
                                "AttributeName": "event_time",
                                "KeyType": "RANGE"
                            }
                        ]
                    },
                    {
                        "IndexName": "EventSourceIndex",
                        "KeySchema": [
                            {
                                "AttributeName": "event_source",
                                "KeyType": "HASH"
                            },
                            {
                                "AttributeName": "event_time",
                                "KeyType": "RANGE"
                            }
                        ]
                    }
                ]
            }
        })

    def test_bucket_lifecycle_policies(self):
        """Test that S3 bucket lifecycle policies are configured"""
        # Production environment should have long-term retention
        self.template.has_resource("AWS::S3::Bucket", {
            "Properties": {
                "LifecycleConfiguration": {
                    "Rules": [
                        {
                            "Id": "ProductionLogsLifecycle",
                            "Status": "Enabled"
                            # No expiration for production logs
                        }
                    ]
                }
            }
        })

    def test_stack_tags_applied(self):
        """Test that proper tags are applied to resources"""
        # DynamoDB tables should have proper tags
        self.template.has_resource("AWS::DynamoDB::Table", {
            "Properties": {
                "Tags": [
                    {
                        "Key": "App",
                        "Value": "bedrock-budgeteer"
                    },
                    {
                        "Key": "Environment",
                        "Value": "production"
                    },
                    {
                        "Key": "Component",
                        "Value": "data-storage"
                    }
                ]
            }
        })


if __name__ == "__main__":
    unittest.main()
