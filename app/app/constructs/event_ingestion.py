"""
Event Ingestion Construct for Bedrock Budgeteer
Manages CloudTrail, EventBridge, and Kinesis Data Firehose for event collection
"""
from typing import Dict, Optional
from aws_cdk import (
    aws_events as events,
    aws_cloudtrail as cloudtrail,
    aws_kinesisfirehose as firehose,
    aws_s3 as s3,
    aws_iam as iam,
    aws_lambda as lambda_,
    aws_logs as logs,
    aws_logs_destinations as logs_destinations,
    aws_kms as kms,
    RemovalPolicy,
    Duration,
    Size,
)
from constructs import Construct


class EventIngestionConstruct(Construct):
    """Construct for event ingestion pipeline including CloudTrail, EventBridge, and Kinesis Firehose"""
    
    def __init__(self, scope: Construct, construct_id: str, 
                 environment_name: str, 
                 s3_bucket: Optional[s3.Bucket] = None,
                 kms_key: Optional[kms.IKey] = None,
                 usage_calculator_function: Optional[lambda_.Function] = None,
                 log_retention_days: Optional[logs.RetentionDays] = None,
                 **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)
        
        self.environment_name = environment_name
        self.s3_bucket = s3_bucket
        self.kms_key = kms_key
        self.usage_calculator_function = usage_calculator_function
        self.log_retention_days = log_retention_days or logs.RetentionDays.ONE_WEEK  # Default to 7 days
        
        # Initialize storage for created resources
        self.cloudtrail_trails: Dict[str, cloudtrail.Trail] = {}
        self.eventbridge_rules: Dict[str, events.Rule] = {}
        self.firehose_streams: Dict[str, firehose.DeliveryStream] = {}
        self.log_groups: Dict[str, logs.LogGroup] = {}
        
        # Environment-specific configurations
        self.removal_policy = self._get_removal_policy()
        
        # Create CloudTrail for API event capture
        self._create_cloudtrail()
        
        # Create EventBridge rules for event routing
        self._create_eventbridge_rules()
        
        # Create Kinesis Data Firehose streams
        self._create_firehose_streams()
        
        # Create Bedrock invocation log group and subscription
        self._create_bedrock_invocation_logs()
        
        # Tags are applied by TaggingFramework aspects
    
    def _should_skip_public_access_block(self) -> bool:
        """Check if S3 public access block should be skipped (for enterprise SCPs)"""
        try:
            return self.node.try_get_context("bedrock-budgeteer:feature-flags").get("skip-s3-public-access-block", False)
        except (AttributeError, TypeError):
            return False
    
    def _get_removal_policy(self) -> RemovalPolicy:
        """Get removal policy for production environment"""
        # Allow resource deletion for proper rollback during deployment failures
        return RemovalPolicy.DESTROY
    
    def _create_cloudtrail(self) -> None:
        """Create CloudTrail for capturing Bedrock and IAM events"""
        
        # Create CloudTrail S3 bucket if not provided
        if not self.s3_bucket:
            cloudtrail_bucket_props = {
                "bucket_name": f"bedrock-budgeteer-{self.environment_name}-cloudtrail",
                "removal_policy": self.removal_policy,
                "encryption": s3.BucketEncryption.S3_MANAGED if not self.kms_key else s3.BucketEncryption.KMS,
                "encryption_key": self.kms_key if self.kms_key else None,
                "lifecycle_rules": [
                    s3.LifecycleRule(
                        id="CloudTrailLogLifecycle",
                        enabled=True,
                        transitions=[
                            s3.Transition(
                                storage_class=s3.StorageClass.INFREQUENT_ACCESS,
                                transition_after=Duration.days(30)
                            ),
                            s3.Transition(
                                storage_class=s3.StorageClass.GLACIER,
                                transition_after=Duration.days(90)
                            ),
                            s3.Transition(
                                storage_class=s3.StorageClass.DEEP_ARCHIVE,
                                transition_after=Duration.days(365)
                            )
                        ]
                    )
                ],
                "public_read_access": False,
                "versioned": False,  # Disable versioning to allow proper deletion
                "auto_delete_objects": True  # Allow CDK to delete objects during bucket deletion
            }
            
            # Only add public access block if not skipped (for enterprise SCPs)
            if not self._should_skip_public_access_block():
                cloudtrail_bucket_props["block_public_access"] = s3.BlockPublicAccess.BLOCK_ALL
                
            self.cloudtrail_bucket = s3.Bucket(self, "CloudTrailBucket", **cloudtrail_bucket_props)
        else:
            self.cloudtrail_bucket = self.s3_bucket
        
        # Create CloudTrail with EventBridge integration
        self.cloudtrail_trails["main"] = cloudtrail.Trail(
            self, "BedrockBudgeteerTrail",
            trail_name=f"bedrock-budgeteer-{self.environment_name}-trail",
            bucket=self.cloudtrail_bucket,
            s3_key_prefix="cloudtrail-logs",
            enable_file_validation=True,
            include_global_service_events=True,
            is_multi_region_trail=True,
            send_to_cloud_watch_logs=True,
            cloud_watch_logs_retention=logs.RetentionDays.ONE_MONTH,
            # Note: EventBridge integration enabled through event rules
        )
        
        # Bedrock API calls are management events, so they're included by default
        # No additional event selectors needed for Bedrock monitoring
        
        # Add S3 data events for tracking S3-based operations in production
        self.cloudtrail_trails["main"].add_s3_event_selector(
            s3_selector=[
                cloudtrail.S3EventSelector(
                    bucket=self.cloudtrail_bucket,
                    object_prefix="bedrock-logs/"
                )
            ],
            read_write_type=cloudtrail.ReadWriteType.ALL,
            include_management_events=False
        )
    
    def _create_eventbridge_rules(self) -> None:
        """Create EventBridge rules for filtering and routing CloudTrail events"""
        
        # Rule for Bedrock API usage events
        self.eventbridge_rules["bedrock_usage"] = events.Rule(
            self, "BedrockUsageRule",
            rule_name=f"bedrock-budgeteer-{self.environment_name}-bedrock-usage",
            description="Capture Bedrock API usage events for cost tracking",
            event_pattern=events.EventPattern(
                source=["aws.bedrock"],
                detail_type=["AWS API Call via CloudTrail"],
                detail={
                    "eventSource": ["bedrock.amazonaws.com"],
                    "eventName": [
                        "InvokeModel",
                        "InvokeModelWithResponseStream",
                        "GetFoundationModel",
                        "ListFoundationModels"
                    ]
                }
            )
        )
        
        # Rule for IAM access key creation events
        self.eventbridge_rules["iam_key_creation"] = events.Rule(
            self, "IAMKeyCreationRule",
            rule_name=f"bedrock-budgeteer-{self.environment_name}-iam-key-creation",
            description="Capture IAM access key creation events",
            event_pattern=events.EventPattern(
                source=["aws.iam"],
                detail_type=["AWS API Call via CloudTrail"],
                detail={
                    "eventSource": ["iam.amazonaws.com"],
                    "eventName": [
                        "CreateUser",
                        "CreateServiceSpecificCredential",
                        "AttachRolePolicy"
                    ]
                }
            )
        )
        
        # Rule for IAM permission changes affecting Bedrock access
        self.eventbridge_rules["iam_bedrock_permissions"] = events.Rule(
            self, "IAMBedrockPermissionsRule",
            rule_name=f"bedrock-budgeteer-{self.environment_name}-iam-bedrock-permissions",
            description="Capture IAM permission changes affecting Bedrock access",
            event_pattern=events.EventPattern(
                source=["aws.iam"],
                detail_type=["AWS API Call via CloudTrail"],
                detail={
                    "eventSource": ["iam.amazonaws.com"],
                    "eventName": [
                        "AttachUserPolicy",
                        "AttachRolePolicy",
                        "DetachUserPolicy", 
                        "DetachRolePolicy",
                        "PutUserPolicy",
                        "PutRolePolicy",
                        "DeleteUserPolicy",
                        "DeleteRolePolicy"
                    ],
                    # Filter for policies that might affect Bedrock access
                    "requestParameters": {
                        "policyDocument": {
                            "Statement": {
                                "Effect": ["Allow"],
                                "Action": ["bedrock:*"]
                            }
                        }
                    }
                }
            )
        )
    
    def _create_firehose_streams(self) -> None:
        """Create Kinesis Data Firehose streams for log data delivery"""
        
        # Create IAM role for Firehose
        firehose_role = iam.Role(
            self, "FirehoseDeliveryRole",
            assumed_by=iam.ServicePrincipal("firehose.amazonaws.com"),
            description="Role for Kinesis Data Firehose to deliver logs"
        )
        
        # Grant permissions to write to S3
        if self.s3_bucket:
            self.s3_bucket.grant_write(firehose_role)
        
        # Grant permissions to use KMS key if provided
        if self.kms_key:
            self.kms_key.grant_encrypt_decrypt(firehose_role)
        
        # Create Firehose stream for Bedrock usage logs with optional data transformation
        if self.usage_calculator_function:
            # Grant Firehose permission to invoke the usage calculator Lambda
            self.usage_calculator_function.grant_invoke(firehose_role)
            
            # Use L1 construct (CfnDeliveryStream) for data transformation support
            self.firehose_streams["bedrock_usage"] = firehose.CfnDeliveryStream(
                self, "BedrockUsageFirehose",
                delivery_stream_name=f"bedrock-budgeteer-{self.environment_name}-usage-logs",
                delivery_stream_type="DirectPut",
                extended_s3_destination_configuration=firehose.CfnDeliveryStream.ExtendedS3DestinationConfigurationProperty(
                    bucket_arn=(self.s3_bucket if self.s3_bucket else self.cloudtrail_bucket).bucket_arn,
                    role_arn=firehose_role.role_arn,
                    prefix="bedrock-usage-logs/year=!{timestamp:yyyy}/month=!{timestamp:MM}/day=!{timestamp:dd}/hour=!{timestamp:HH}/",
                    error_output_prefix="errors/",
                    buffering_hints=firehose.CfnDeliveryStream.BufferingHintsProperty(
                        interval_in_seconds=300,
                        size_in_m_bs=5
                    ),
                    compression_format="GZIP",
                    processing_configuration=firehose.CfnDeliveryStream.ProcessingConfigurationProperty(
                        enabled=True,
                        processors=[
                            firehose.CfnDeliveryStream.ProcessorProperty(
                                type="Lambda",
                                parameters=[
                                    firehose.CfnDeliveryStream.ProcessorParameterProperty(
                                        parameter_name="LambdaArn",
                                        parameter_value=self.usage_calculator_function.function_arn
                                    )
                                ]
                            )
                        ]
                    )
                )
            )
        else:
            # Use L2 construct without data transformation
            self.firehose_streams["bedrock_usage"] = firehose.DeliveryStream(
                self, "BedrockUsageFirehose",
                delivery_stream_name=f"bedrock-budgeteer-{self.environment_name}-usage-logs",
                destination=firehose.S3Bucket(
                    bucket=self.s3_bucket if self.s3_bucket else self.cloudtrail_bucket,
                    data_output_prefix="bedrock-usage-logs/year=!{timestamp:yyyy}/month=!{timestamp:MM}/day=!{timestamp:dd}/hour=!{timestamp:HH}/",
                    error_output_prefix="errors/",
                    buffering_interval=Duration.seconds(300),
                    buffering_size=Size.mebibytes(5),
                    compression=firehose.Compression.GZIP,
                    role=firehose_role
                )
            )
        
        # Create Firehose stream for audit logs
        self.firehose_streams["audit_logs"] = firehose.DeliveryStream(
            self, "AuditLogsFirehose",
            delivery_stream_name=f"bedrock-budgeteer-{self.environment_name}-audit-logs",
            destination=firehose.S3Bucket(
                bucket=self.s3_bucket if self.s3_bucket else self.cloudtrail_bucket,
                data_output_prefix="audit-logs/year=!{timestamp:yyyy}/month=!{timestamp:MM}/day=!{timestamp:dd}/hour=!{timestamp:HH}/",
                error_output_prefix="audit-errors/",
                buffering_interval=Duration.seconds(60),
                buffering_size=Size.mebibytes(3),
                compression=firehose.Compression.GZIP,
                role=firehose_role
            )
        )
    
    def _create_bedrock_invocation_logs(self) -> None:
        """Create CloudWatch log group for Bedrock invocation logs and subscription to Firehose"""
        
        # Create log group with KMS encryption if available
        log_group_props = {
            "log_group_name": f"/aws/bedrock/bedrock-budgeteer-{self.environment_name}-invocation-logs",
            "retention": self.log_retention_days,
            "removal_policy": self.removal_policy
        }
        
        # Add KMS encryption if key is provided
        if self.kms_key:
            log_group_props["encryption_key"] = self.kms_key
        
        self.log_groups["bedrock_invocation"] = logs.LogGroup(
            self, "BedrockInvocationLogGroup",
            **log_group_props
        )
        
        # Create IAM role for CloudWatch Logs to write to Firehose
        logs_to_firehose_role = iam.Role(
            self, "BedrockLogsToFirehoseRole",
            assumed_by=iam.ServicePrincipal("logs.amazonaws.com"),
            description="Role for CloudWatch Logs to stream Bedrock logs to Firehose"
        )
        
        # Grant permissions to put records to Firehose
        # Handle both L1 (CfnDeliveryStream) and L2 (DeliveryStream) constructs
        if hasattr(self.firehose_streams["bedrock_usage"], 'delivery_stream_arn'):
            # L2 construct
            firehose_arn = self.firehose_streams["bedrock_usage"].delivery_stream_arn
        else:
            # L1 construct - construct ARN manually
            firehose_arn = f"arn:aws:firehose:*:*:deliverystream/bedrock-budgeteer-{self.environment_name}-usage-logs"
        
        logs_to_firehose_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=["firehose:PutRecord", "firehose:PutRecordBatch"],
                resources=[firehose_arn]
            )
        )
        
        # Grant permissions to use KMS key if provided
        if self.kms_key:
            self.kms_key.grant_encrypt_decrypt(logs_to_firehose_role)
        
        # Create subscription filter to stream logs to Firehose
        # Note: We need to use a custom destination since CDK doesn't have a built-in Firehose destination
        logs.SubscriptionFilter(
            self, "BedrockLogsSubscription",
            log_group=self.log_groups["bedrock_invocation"],
            destination=logs_destinations.LambdaDestination(
                # We'll create a simple Lambda that forwards to Firehose
                self._create_logs_to_firehose_lambda(logs_to_firehose_role)
            ),
            filter_pattern=logs.FilterPattern.all_events(),
            filter_name=f"bedrock-budgeteer-{self.environment_name}-invocation-logs"
        )
    
    def _create_logs_to_firehose_lambda(self, firehose_role: iam.Role) -> lambda_.Function:
        """Create a Lambda function to forward CloudWatch Logs to Kinesis Data Firehose"""
        
        # Create execution role for the Lambda
        lambda_role = iam.Role(
            self, "LogsToFirehoseLambdaRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name("service-role/AWSLambdaBasicExecutionRole")
            ]
        )
        
        # Grant permissions to put records to Firehose
        # Use the same firehose ARN logic as above
        if hasattr(self.firehose_streams["bedrock_usage"], 'delivery_stream_arn'):
            # L2 construct
            firehose_arn = self.firehose_streams["bedrock_usage"].delivery_stream_arn
        else:
            # L1 construct - construct ARN manually
            firehose_arn = f"arn:aws:firehose:*:*:deliverystream/bedrock-budgeteer-{self.environment_name}-usage-logs"
        
        lambda_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=["firehose:PutRecord", "firehose:PutRecordBatch"],
                resources=[firehose_arn]
            )
        )
        
        # Grant permissions to use KMS key if provided
        if self.kms_key:
            self.kms_key.grant_encrypt_decrypt(lambda_role)
        
        # Create the Lambda function
        logs_forwarder = lambda_.Function(
            self, "LogsToFirehoseLambda",
            function_name=f"bedrock-budgeteer-{self.environment_name}-logs-forwarder",
            runtime=lambda_.Runtime.PYTHON_3_9,
            handler="index.lambda_handler",
            role=lambda_role,
            code=lambda_.Code.from_inline(f"""
import json
import boto3
import gzip
import base64
import time
import logging

logger = logging.getLogger()
logger.setLevel(logging.INFO)

firehose = boto3.client('firehose')
DELIVERY_STREAM_NAME = 'bedrock-budgeteer-{self.environment_name}-usage-logs'

def lambda_handler(event, context):
    \"\"\"Forward CloudWatch Logs to Kinesis Data Firehose\"\"\"
    
    # Decode CloudWatch Logs data
    cdata = event['awslogs']['data']
    compressed_data = base64.b64decode(cdata)
    uncompressed_data = gzip.decompress(compressed_data)
    log_data = json.loads(uncompressed_data)
    
    # Process each log event
    records = []
    for log_event in log_data['logEvents']:
        # Enrich the log event with metadata from CloudWatch log group
        enriched_event = log_event.copy()
        
        # Extract principal ID from log group or log stream if available
        # Log stream name might contain user info: e.g., "user-123/stream-456"
        log_stream = log_data.get('logStream', '')
        
        # Try to extract principal from log stream name (format may vary)
        principal_id = None
        if '/' in log_stream:
            parts = log_stream.split('/')
            # Look for user-like identifiers
            for part in parts:
                if part.startswith('user-') or part.startswith('BedrockAPIKey-'):
                    principal_id = part
                    break
        
        # Add metadata to the log event
        enriched_event['_metadata'] = {{
            'logGroup': log_data.get('logGroup', ''),
            'logStream': log_stream,
            'principal_id': principal_id,
            'timestamp': log_event.get('timestamp'),
            'processed_at': int(time.time() * 1000)
        }}
        
        # Forward the enriched log event to Firehose
        record = {{
            'Data': json.dumps(enriched_event) + '\\n'
        }}
        records.append(record)
    
    # Send to Firehose in batches
    if records:
        try:
            response = firehose.put_record_batch(
                DeliveryStreamName=DELIVERY_STREAM_NAME,
                Records=records
            )
            logger.info(f"Successfully sent {{len(records)}} records to Firehose")
            return {{'statusCode': 200, 'recordsProcessed': len(records)}}
        except Exception as e:
            logger.error(f"Error sending to Firehose: {{e}}")
            raise
    
    return {{'statusCode': 200, 'recordsProcessed': 0}}
"""),
            timeout=Duration.minutes(5),
            memory_size=256,
            description="Forwards CloudWatch Logs from Bedrock invocation logs to Kinesis Data Firehose"
        )
        
        return logs_forwarder
    
    def add_eventbridge_target(self, rule_name: str, target) -> None:
        """Add a target to an existing EventBridge rule"""
        if rule_name in self.eventbridge_rules:
            self.eventbridge_rules[rule_name].add_target(target)
        else:
            raise ValueError(f"EventBridge rule '{rule_name}' not found")
    
    def configure_usage_calculator(self, usage_calculator_function: lambda_.Function) -> None:
        """Configure the usage calculator Lambda for real-time processing via Firehose data transformation"""
        if not usage_calculator_function:
            return
            
        # Store the function reference
        self.usage_calculator_function = usage_calculator_function
        
        # Note: CDK doesn't support updating resources after creation.
        # This method is kept for future extensibility but the actual
        # configuration should be done during initial construction.
        # For now, we'll need to recreate the stack to apply changes.
    
    def add_firehose_lambda_destination(self, stream_name: str, lambda_function: lambda_.Function) -> None:
        """Add a Lambda destination to an existing Firehose stream"""
        # Note: This would require extending the Firehose configuration
        # For now, we'll use EventBridge -> Lambda pattern instead
        pass
    

    
    @property
    def cloudtrail_bucket_name(self) -> str:
        """Get the CloudTrail S3 bucket name"""
        if hasattr(self, 'cloudtrail_bucket'):
            return self.cloudtrail_bucket.bucket_name
        elif self.s3_bucket:
            return self.s3_bucket.bucket_name
        return ""
    
    @property
    def firehose_delivery_role_arn(self) -> str:
        """Get the Firehose delivery role ARN for use by other constructs"""
        # This would be available after the role is created
        # Implementation depends on how we expose internal resources
        return ""
    
    @property
    def bedrock_invocation_log_group(self) -> logs.LogGroup:
        """Get the Bedrock invocation log group"""
        return self.log_groups["bedrock_invocation"]
    
    @property
    def bedrock_invocation_log_group_arn(self) -> str:
        """Get the Bedrock invocation log group ARN"""
        return self.log_groups["bedrock_invocation"].log_group_arn
