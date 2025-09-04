"""
Bedrock Budgeteer Main Application Stack
Orchestrates all components of the budget monitoring system
"""
import os
from typing import Dict, Any, Optional
from aws_cdk import (
    Stack,
    aws_kms as kms,
)
from constructs import Construct

# Import our custom constructs
from .constructs.data_storage import DataStorageConstruct
from .constructs.security import SecurityConstruct
from .constructs.monitoring import MonitoringConstruct
from .constructs.tagging import TaggingFramework
from .constructs.configuration import ConfigurationConstruct
from .constructs.event_ingestion import EventIngestionConstruct
from .constructs.log_storage import LogStorageConstruct
from .constructs.core_processing import CoreProcessingConstruct
from .constructs.workflow_orchestration import WorkflowOrchestrationConstruct
# Operational controls removed per changelog - see 2025-09-02 updates



class BedrockBudgeteerStack(Stack):
    """Main application stack for Bedrock Budgeteer system"""

    def __init__(self, scope: Construct, construct_id: str, 
                 environment_name: str = "production",
                 kms_key: Optional[kms.IKey] = None,
                 **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)
        
        self.environment_name = environment_name
        self.kms_key = kms_key  # User-provided KMS key (optional)
        
        # Initialize tagging framework first (applies to all subsequent resources)
        self.tagging_framework = TaggingFramework(
            self, "TaggingFramework",
            environment_name=environment_name
        )
        
        # Tags are applied by TaggingFramework aspects
        
        # Initialize core constructs
        self.security = SecurityConstruct(
            self, "Security",
            environment_name=environment_name
        )
        
        self.data_storage = DataStorageConstruct(
            self, "DataStorage", 
            environment_name=environment_name,
            kms_key=self.kms_key
        )
        
        # Initialize log storage with user-provided KMS key
        self.log_storage = LogStorageConstruct(
            self, "LogStorage",
            environment_name=environment_name,
            kms_key=self.kms_key
        )
        
        # Create configuration management
        self.configuration = ConfigurationConstruct(
            self, "Configuration",
            environment_name=environment_name,
            kms_key=self.kms_key
        )
        
        # Initialize core processing Lambda functions first (needed for event ingestion)
        self.core_processing = CoreProcessingConstruct(
            self, "CoreProcessing",
            environment_name=environment_name,
            dynamodb_tables=self.data_storage.tables,
            s3_bucket=self.log_storage.logs_bucket,
            lambda_execution_role=self.security.roles["lambda_execution"],
            kms_key=self.kms_key
        )
        
        # Initialize event ingestion with usage calculator for real-time processing
        self.event_ingestion = EventIngestionConstruct(
            self, "EventIngestion",
            environment_name=environment_name,
            s3_bucket=self.log_storage.logs_bucket,
            kms_key=self.kms_key,
            usage_calculator_function=self.core_processing.functions["usage_calculator"]
        )
        
        self.monitoring = MonitoringConstruct(
            self, "Monitoring",
            environment_name=environment_name
        )
        
        # Initialize workflow orchestration
        self.workflow_orchestration = WorkflowOrchestrationConstruct(
            self, "WorkflowOrchestration",
            environment_name=environment_name,
            dynamodb_tables=self.data_storage.tables,
            lambda_functions=self.core_processing.functions,
            step_functions_role=self.security.roles["step_functions"],
            lambda_execution_role=self.security.roles["lambda_execution"],
            sns_topics=self.monitoring.topics,
            kms_key=self.kms_key
        )
        
        # Add additional permissions to security roles
        self._configure_security_permissions()
        
        # Set up monitoring for created resources
        self._setup_monitoring()
        
        # Set up ingestion pipeline monitoring
        self._setup_ingestion_monitoring()
        
        # Set up core processing monitoring
        self._setup_core_processing_monitoring()
        
        # Set up workflow orchestration monitoring
        self._setup_workflow_monitoring()
        
        # Enable Phase 5: Advanced notifications and business metrics
        self._enable_phase5_features()
        
        # Phase 6: Operational Controls removed per changelog - see 2025-09-02 updates
        # Emergency controls, circuit breakers, and maintenance mode no longer needed
        
        # Note: Log group deletion policies are handled by disabling CDK auto-creation
        # and managing log groups explicitly with RemovalPolicy.DESTROY where needed
    

    
    def _configure_security_permissions(self) -> None:
        """Configure additional security permissions for service integration"""
        # Add Bedrock permissions for cost monitoring
        self.security.add_bedrock_permissions()
        
        # Add Pricing API permissions for cost calculation
        self.security.add_pricing_api_permissions()
        
        # Add CloudTrail permissions for usage tracking
        self.security.add_cloudtrail_permissions()
        
        # Add SSM permissions for configuration access
        self.security.add_ssm_permissions()
        
        # Add IAM read permissions for policy management
        self.security.add_iam_read_permissions()
        
        # Add CloudWatch metrics permissions
        self.security.add_cloudwatch_metrics_permissions()
        
        # Add DynamoDB permissions for core processing tables
        self.security.add_dynamodb_permissions(self.data_storage.tables)
        
        # Add S3 permissions for log processing
        self.security.add_s3_permissions(self.log_storage.logs_bucket)
        
        # Add SQS permissions for DLQ access
        self.security.add_sqs_permissions(self.core_processing.dead_letter_queues)
    
    def _setup_monitoring(self) -> None:
        """Set up monitoring for all created resources"""
        # Add monitoring for DynamoDB tables
        for table_name, table in self.data_storage.tables.items():
            self.monitoring.add_dynamodb_monitoring(table_name, table)
        
        # Add email subscriptions if environment variables are set
        ops_email = os.getenv("OPS_EMAIL")
        if ops_email:
            self.monitoring.add_email_subscription("high_severity", ops_email)
            self.monitoring.add_email_subscription("operational_alerts", ops_email)
    
    def _setup_ingestion_monitoring(self) -> None:
        """Set up monitoring for the ingestion pipeline"""
        # Create ingestion pipeline dashboard
        self.monitoring.create_ingestion_pipeline_dashboard()
        
        # Add monitoring for CloudTrail trails
        for trail_name, trail in self.event_ingestion.cloudtrail_trails.items():
            self.monitoring.add_cloudtrail_monitoring(trail_name, trail)
        
        # Add monitoring for EventBridge rules
        for rule_name, rule in self.event_ingestion.eventbridge_rules.items():
            self.monitoring.add_eventbridge_monitoring(rule_name, rule)
        
        # Add monitoring for Firehose streams
        for stream_name, stream in self.event_ingestion.firehose_streams.items():
            self.monitoring.add_firehose_monitoring(stream_name, stream)
        
        # Add monitoring for S3 buckets
        for bucket_name, bucket in self.log_storage.buckets.items():
            self.monitoring.add_s3_monitoring(bucket_name, bucket)
        
        # Add monitoring for CloudWatch log groups (Bedrock invocation logs)
        for log_group_name, log_group in self.event_ingestion.log_groups.items():
            self.monitoring.add_log_group_monitoring(log_group_name, log_group)
    
    def _setup_core_processing_monitoring(self) -> None:
        """Set up monitoring for core processing Lambda functions"""
        # Add monitoring for Lambda functions
        for function_name, function in self.core_processing.functions.items():
            self.monitoring.add_lambda_monitoring(function_name, function)
        
        # Add monitoring for DLQ queues
        for queue_name, queue in self.core_processing.dead_letter_queues.items():
            self.monitoring.add_sqs_monitoring(f"{queue_name}_dlq", queue)
    
    def _setup_workflow_monitoring(self) -> None:
        """Set up monitoring for workflow orchestration"""
        # Add monitoring for workflow Lambda functions
        for function_name, function in self.workflow_orchestration.workflow_functions.items():
            self.monitoring.add_lambda_monitoring(f"workflow_{function_name}", function)
        
        # Add monitoring for workflow DLQ queues
        for queue_name, queue in self.workflow_orchestration.workflow_dlqs.items():
            self.monitoring.add_sqs_monitoring(f"workflow_{queue_name}_dlq", queue)
        
        # Add monitoring for Step Functions state machines
        for machine_name, machine in self.workflow_orchestration.state_machines.items():
            self.monitoring.add_stepfunctions_monitoring(machine_name, machine)
        
        # Create workflow dashboard
        self.monitoring.create_workflow_dashboard()
    
    def _enable_phase5_features(self) -> None:
        """Enable Phase 5 advanced monitoring and notification features"""
        # Create custom business metrics and alarms
        self.monitoring.create_custom_business_metrics()
        
        # Set up multi-channel notifications based on environment
        self._setup_notification_channels()
    
    def _setup_notification_channels(self) -> None:
        """Set up multi-channel notification integrations"""
        # Add notification channels
        slack_webhook = os.getenv("SLACK_WEBHOOK_URL")
        if slack_webhook:
            self.monitoring.add_slack_subscription("high_severity", slack_webhook)
            self.monitoring.add_slack_subscription("operational_alerts", slack_webhook)
        
        # SMS for critical budget alerts
        ops_phone = os.getenv("OPS_PHONE_NUMBER")
        if ops_phone:
            self.monitoring.add_sms_subscription("high_severity", ops_phone)
        
        # Generic webhook for external integrations
        webhook_url = os.getenv("EXTERNAL_WEBHOOK_URL")
        if webhook_url:
            webhook_headers = {
                "Authorization": f"Bearer {os.getenv('WEBHOOK_AUTH_TOKEN', '')}",
                "X-Source": "bedrock-budgeteer"
            }
            self.monitoring.add_webhook_subscription("budget_alerts", webhook_url, webhook_headers)
        
        # Email notifications
        ops_email = os.getenv("OPS_EMAIL")
        if not ops_email:
            # Fallback to CDK context alert-email if environment variable not set
            ops_email = self.node.try_get_context("bedrock-budgeteer:config")
            if ops_email:
                ops_email = ops_email.get("alert-email")
        
        if ops_email:
            self.monitoring.add_email_subscription("operational_alerts", ops_email)
            self.monitoring.add_email_subscription("budget_alerts", ops_email)
            self.monitoring.add_email_subscription("high_severity", ops_email)
    
    @property
    def dynamodb_tables(self) -> Dict[str, Any]:
        """Expose DynamoDB tables for use by other constructs"""
        return self.data_storage.tables
    
    @property
    def iam_roles(self) -> Dict[str, Any]:
        """Expose IAM roles for use by other constructs"""
        return self.security.roles
    
    @property
    def sns_topics(self) -> Dict[str, Any]:
        """Expose SNS topics for use by other constructs"""
        return self.monitoring.topics
    
    @property
    def s3_buckets(self) -> Dict[str, Any]:
        """Expose S3 buckets for use by other constructs"""
        return self.log_storage.buckets
    
    @property
    def cloudtrail_trails(self) -> Dict[str, Any]:
        """Expose CloudTrail trails for use by other constructs"""
        return self.event_ingestion.cloudtrail_trails
    
    @property
    def eventbridge_rules(self) -> Dict[str, Any]:
        """Expose EventBridge rules for use by other constructs"""
        return self.event_ingestion.eventbridge_rules
    
    @property
    def firehose_streams(self) -> Dict[str, Any]:
        """Expose Kinesis Firehose streams for use by other constructs"""
        return self.event_ingestion.firehose_streams
    
    @property
    def lambda_functions(self) -> Dict[str, Any]:
        """Expose Lambda functions for use by other constructs"""
        return self.core_processing.functions
    
    @property
    def dlq_queues(self) -> Dict[str, Any]:
        """Expose dead letter queues for monitoring"""
        return self.core_processing.dead_letter_queues
    
    @property
    def step_functions_state_machines(self) -> Dict[str, Any]:
        """Expose Step Functions state machines"""
        return {
            "suspension": self.workflow_orchestration.suspension_state_machine,
            "restoration": self.workflow_orchestration.restoration_state_machine
        }
    
    @property
    def workflow_functions(self) -> Dict[str, Any]:
        """Expose workflow Lambda functions"""
        return self.workflow_orchestration.workflow_functions
    
    # Operational control functions and circuit breaker parameters removed
    # per changelog - see 2025-09-02 updates
    
    @property
    def bedrock_logging_role_arn(self) -> str:
        """Get the Bedrock logging role ARN for console configuration"""
        return self.security.bedrock_logging_role.role_arn
    
    @property
    def bedrock_invocation_log_group_name(self) -> str:
        """Get the Bedrock invocation log group name for console configuration"""
        return self.event_ingestion.bedrock_invocation_log_group.log_group_name


# Legacy class name for backward compatibility  
class AppStack(BedrockBudgeteerStack):
    """Backward compatibility wrapper"""
    pass
