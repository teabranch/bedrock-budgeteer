"""
Monitoring Construct for Bedrock Budgeteer
Manages CloudWatch resources, dashboards, and alarms
Implements Phase 5: Notifications & Monitoring
"""
from typing import Dict, Optional
from aws_cdk import (
    aws_cloudwatch as cloudwatch,
    aws_cloudwatch_actions as cloudwatch_actions,
    aws_logs as logs,
    aws_sns as sns,
    aws_sns_subscriptions as sns_subs,
    aws_iam as iam,
    Duration,
    RemovalPolicy,
)
from constructs import Construct


class MonitoringConstruct(Construct):
    """Construct for CloudWatch monitoring, dashboards, and alarms"""
    
    def __init__(self, scope: Construct, construct_id: str, 
                 environment_name: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)
        
        self.environment_name = environment_name
        self.log_groups: Dict[str, logs.LogGroup] = {}
        self.alarms: Dict[str, cloudwatch.Alarm] = {}
        self.topics: Dict[str, sns.Topic] = {}
        
        # Environment-specific configurations
        self.log_retention = self._get_log_retention()
        self.alarm_thresholds = self._get_alarm_thresholds()
        
        # Create resources
        self._create_sns_topics()
        self._create_dashboard()
        
        # Tags are applied by TaggingFramework aspects
    
    def _get_log_retention(self) -> logs.RetentionDays:
        """Get log retention for production environment"""
        # All log groups must retain data for 30 days
        return logs.RetentionDays.ONE_MONTH
    
    def _get_alarm_thresholds(self) -> Dict[str, Dict[str, float]]:
        """Get alarm thresholds for production environment"""
        # Production environment uses strict thresholds
        return {
            "error_rate": 1.0,
            "latency_p99": 1000.0,
            "invocation_rate": 100.0
        }
    
    def create_lambda_log_group(self, function_name: str) -> logs.LogGroup:
        """Create a log group for a Lambda function with proper deletion policy"""
        log_group = logs.LogGroup(
            self, f"{function_name}LogGroup",
            log_group_name=f"/aws/lambda/bedrock-budgeteer-{function_name}-{self.environment_name}",
            retention=self.log_retention,
            removal_policy=RemovalPolicy.DESTROY  # Ensure proper deletion during rollback
        )
        
        self.log_groups[function_name] = log_group
        return log_group
    
    def _create_sns_topics(self) -> None:
        """Create SNS topics for alerts and notifications"""
        # Operational alerts topic
        self.topics["operational_alerts"] = sns.Topic(
            self, "OperationalAlertsTopic",
            topic_name=f"bedrock-budgeteer-{self.environment_name}-operational-alerts",
            display_name="Bedrock Budgeteer Operational Alerts"
        )
        
        # Budget alerts topic
        self.topics["budget_alerts"] = sns.Topic(
            self, "BudgetAlertsTopic", 
            topic_name=f"bedrock-budgeteer-{self.environment_name}-budget-alerts",
            display_name="Bedrock Budgeteer Budget Alerts"
        )
        
        # High severity alerts topic
        self.topics["high_severity"] = sns.Topic(
            self, "HighSeverityTopic",
            topic_name=f"bedrock-budgeteer-{self.environment_name}-high-severity",
            display_name="Bedrock Budgeteer High Severity Alerts"
        )
    
    def _create_dashboard(self) -> None:
        """Create CloudWatch dashboard for system monitoring"""
        self.dashboard = cloudwatch.Dashboard(
            self, "SystemDashboard",
            dashboard_name=f"bedrock-budgeteer-{self.environment_name}-system"
        )
        
        # Add placeholder widgets - will be populated when Lambda functions are created
        self.dashboard.add_widgets(
            cloudwatch.TextWidget(
                markdown=f"# Bedrock Budgeteer - {self.environment_name.upper()}\n\nSystem Overview Dashboard",
                width=24,
                height=2
            )
        )
    
    def add_lambda_monitoring(self, function_name: str, lambda_function) -> None:
        """Add monitoring for a Lambda function"""
        # Create error rate alarm
        error_alarm = cloudwatch.Alarm(
            self, f"{function_name}ErrorAlarm",
            alarm_name=f"bedrock-budgeteer-{self.environment_name}-{function_name}-errors",
            alarm_description=f"High error rate for {function_name}",
            metric=lambda_function.metric_errors(
                period=Duration.minutes(5),
                statistic="Sum"
            ),
            threshold=self.alarm_thresholds["error_rate"],
            evaluation_periods=2,
            treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING
        )
        
        # Add to high severity topic for production environment
        error_alarm.add_alarm_action(
            cloudwatch_actions.SnsAction(self.topics["high_severity"])
        )
        
        self.alarms[f"{function_name}_errors"] = error_alarm
        
        # Create duration alarm
        duration_alarm = cloudwatch.Alarm(
            self, f"{function_name}DurationAlarm",
            alarm_name=f"bedrock-budgeteer-{self.environment_name}-{function_name}-duration",
            alarm_description=f"High duration for {function_name}",
            metric=lambda_function.metric_duration(
                period=Duration.minutes(5),
                statistic="p99"
            ),
            threshold=self.alarm_thresholds["latency_p99"],
            evaluation_periods=2,
            treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING
        )
        
        duration_alarm.add_alarm_action(
            cloudwatch_actions.SnsAction(self.topics["operational_alerts"])
        )
        
        self.alarms[f"{function_name}_duration"] = duration_alarm
        
        # Add widgets to dashboard
        self._add_lambda_widgets(function_name, lambda_function)
    
    def _add_lambda_widgets(self, function_name: str, lambda_function) -> None:
        """Add Lambda function widgets to dashboard"""
        # Invocation count widget
        invocation_widget = cloudwatch.GraphWidget(
            title=f"{function_name} - Invocations",
            left=[lambda_function.metric_invocations()],
            width=12,
            height=6
        )
        
        # Error rate widget
        error_widget = cloudwatch.GraphWidget(
            title=f"{function_name} - Errors", 
            left=[lambda_function.metric_errors()],
            width=12,
            height=6
        )
        
        # Duration widget
        duration_widget = cloudwatch.GraphWidget(
            title=f"{function_name} - Duration",
            left=[
                lambda_function.metric_duration(statistic="Average"),
                lambda_function.metric_duration(statistic="p99")
            ],
            width=12,
            height=6
        )
        
        # Throttles widget
        throttle_widget = cloudwatch.GraphWidget(
            title=f"{function_name} - Throttles",
            left=[lambda_function.metric_throttles()],
            width=12,
            height=6
        )
        
        self.dashboard.add_widgets(
            invocation_widget, error_widget,
            duration_widget, throttle_widget
        )
    
    def add_dynamodb_monitoring(self, table_name: str, table) -> None:
        """Add monitoring for a DynamoDB table"""
        # Create throttle alarm for reads
        read_throttle_alarm = cloudwatch.Alarm(
            self, f"{table_name}ReadThrottleAlarm",
            alarm_name=f"bedrock-budgeteer-{self.environment_name}-{table_name}-read-throttles",
            alarm_description=f"Read throttles for {table_name} table",
            metric=table.metric_throttled_requests_for_operation(operation="GetItem"),
            threshold=5,
            evaluation_periods=2
        )
        
        read_throttle_alarm.add_alarm_action(
            cloudwatch_actions.SnsAction(self.topics["operational_alerts"])
        )
        
        self.alarms[f"{table_name}_read_throttles"] = read_throttle_alarm
        
        # Add DynamoDB widgets to dashboard
        self._add_dynamodb_widgets(table_name, table)
    
    def _add_dynamodb_widgets(self, table_name: str, table) -> None:
        """Add DynamoDB table widgets to dashboard"""
        # Read/Write capacity widget
        capacity_widget = cloudwatch.GraphWidget(
            title=f"{table_name} - Read/Write Capacity",
            left=[
                table.metric_consumed_read_capacity_units(),
                table.metric_consumed_write_capacity_units()
            ],
            width=12,
            height=6
        )
        
        # Throttle widget
        throttle_widget = cloudwatch.GraphWidget(
            title=f"{table_name} - Throttles",
            left=[
                table.metric_user_errors(),
                table.metric_throttled_requests_for_operation(operation="GetItem")
            ],
            width=12,
            height=6
        )
        
        self.dashboard.add_widgets(capacity_widget, throttle_widget)
    
    def add_cloudtrail_monitoring(self, trail_name: str, trail) -> None:
        """Add monitoring for CloudTrail"""
        # CloudTrail error alarm
        cloudtrail_error_alarm = cloudwatch.Alarm(
            self, f"{trail_name}ErrorAlarm",
            alarm_name=f"bedrock-budgeteer-{self.environment_name}-{trail_name}-errors",
            alarm_description=f"CloudTrail errors for {trail_name}",
            metric=cloudwatch.Metric(
                namespace="AWS/CloudTrail",
                metric_name="ErrorCount",
                dimensions_map={"TrailName": trail_name},
                period=Duration.minutes(5),
                statistic="Sum"
            ),
            threshold=1,
            evaluation_periods=1,
            treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING
        )
        
        cloudtrail_error_alarm.add_alarm_action(
            cloudwatch_actions.SnsAction(self.topics["operational_alerts"])
        )
        
        self.alarms[f"{trail_name}_errors"] = cloudtrail_error_alarm
        
        # Add CloudTrail widget to dashboard
        cloudtrail_widget = cloudwatch.GraphWidget(
            title=f"CloudTrail {trail_name} - Event Count",
            left=[
                cloudwatch.Metric(
                    namespace="AWS/CloudTrail",
                    metric_name="EventCount",
                    dimensions_map={"TrailName": trail_name},
                    period=Duration.minutes(5),
                    statistic="Sum"
                )
            ],
            width=12,
            height=6
        )
        
        self.dashboard.add_widgets(cloudtrail_widget)
    
    def add_eventbridge_monitoring(self, rule_name: str, rule) -> None:
        """Add monitoring for EventBridge rules"""
        # Rule invocation alarm
        rule_invocation_alarm = cloudwatch.Alarm(
            self, f"{rule_name}InvocationAlarm",
            alarm_name=f"bedrock-budgeteer-{self.environment_name}-{rule_name}-invocations",
            alarm_description=f"EventBridge rule invocations for {rule_name}",
            metric=cloudwatch.Metric(
                namespace="AWS/Events",
                metric_name="InvocationsCount",
                dimensions_map={"RuleName": rule.rule_name},
                period=Duration.minutes(5),
                statistic="Sum"
            ),
            threshold=1000,  # Adjust based on expected volume
            evaluation_periods=3,
            comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
            treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING
        )
        
        rule_invocation_alarm.add_alarm_action(
            cloudwatch_actions.SnsAction(self.topics["operational_alerts"])
        )
        
        self.alarms[f"{rule_name}_invocations"] = rule_invocation_alarm
        
        # Failed invocations alarm
        rule_failed_alarm = cloudwatch.Alarm(
            self, f"{rule_name}FailedAlarm",
            alarm_name=f"bedrock-budgeteer-{self.environment_name}-{rule_name}-failed",
            alarm_description=f"EventBridge rule failed invocations for {rule_name}",
            metric=cloudwatch.Metric(
                namespace="AWS/Events",
                metric_name="FailedInvocationsCount",
                dimensions_map={"RuleName": rule.rule_name},
                period=Duration.minutes(5),
                statistic="Sum"
            ),
            threshold=1,
            evaluation_periods=1,
            treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING
        )
        
        rule_failed_alarm.add_alarm_action(
            cloudwatch_actions.SnsAction(self.topics["high_severity"])
        )
        
        self.alarms[f"{rule_name}_failed"] = rule_failed_alarm
        
        # Add EventBridge widgets to dashboard
        eventbridge_widget = cloudwatch.GraphWidget(
            title=f"EventBridge {rule_name} - Invocations",
            left=[
                cloudwatch.Metric(
                    namespace="AWS/Events",
                    metric_name="InvocationsCount",
                    dimensions_map={"RuleName": rule.rule_name},
                    period=Duration.minutes(5),
                    statistic="Sum"
                ),
                cloudwatch.Metric(
                    namespace="AWS/Events",
                    metric_name="FailedInvocationsCount",
                    dimensions_map={"RuleName": rule.rule_name},
                    period=Duration.minutes(5),
                    statistic="Sum"
                )
            ],
            width=12,
            height=6
        )
        
        self.dashboard.add_widgets(eventbridge_widget)
    
    def add_firehose_monitoring(self, stream_name: str, stream) -> None:
        """Add monitoring for Kinesis Data Firehose"""
        # Delivery failure alarm
        delivery_failure_alarm = cloudwatch.Alarm(
            self, f"{stream_name}DeliveryFailureAlarm",
            alarm_name=f"bedrock-budgeteer-{self.environment_name}-{stream_name}-delivery-failures",
            alarm_description=f"Firehose delivery failures for {stream_name}",
            metric=cloudwatch.Metric(
                namespace="AWS/KinesisFirehose",
                metric_name="DeliveryToS3.DataFreshness",
                dimensions_map={"DeliveryStreamName": stream.delivery_stream_name},
                period=Duration.minutes(5),
                statistic="Maximum"
            ),
            threshold=900,  # 15 minutes
            evaluation_periods=2,
            comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
            treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING
        )
        
        delivery_failure_alarm.add_alarm_action(
            cloudwatch_actions.SnsAction(self.topics["operational_alerts"])
        )
        
        self.alarms[f"{stream_name}_delivery_failures"] = delivery_failure_alarm
        
        # Add Firehose widgets to dashboard
        firehose_widget = cloudwatch.GraphWidget(
            title=f"Firehose {stream_name} - Delivery Metrics",
            left=[
                cloudwatch.Metric(
                    namespace="AWS/KinesisFirehose",
                    metric_name="DeliveryToS3.Records",
                    dimensions_map={"DeliveryStreamName": stream.delivery_stream_name},
                    period=Duration.minutes(5),
                    statistic="Sum"
                ),
                cloudwatch.Metric(
                    namespace="AWS/KinesisFirehose",
                    metric_name="DeliveryToS3.DataFreshness",
                    dimensions_map={"DeliveryStreamName": stream.delivery_stream_name},
                    period=Duration.minutes(5),
                    statistic="Maximum"
                )
            ],
            width=12,
            height=6
        )
        
        self.dashboard.add_widgets(firehose_widget)
    
    def add_sqs_monitoring(self, queue_name: str, queue) -> None:
        """Add monitoring for an SQS queue"""
        # Create alarm for queue depth
        queue_depth_alarm = cloudwatch.Alarm(
            self, f"{queue_name}DepthAlarm",
            alarm_name=f"bedrock-budgeteer-{self.environment_name}-{queue_name}-depth",
            alarm_description=f"Message count for {queue_name} queue",
            metric=queue.metric_approximate_number_of_messages_visible(),
            threshold=10,
            evaluation_periods=2
        )
        
        queue_depth_alarm.add_alarm_action(
            cloudwatch_actions.SnsAction(self.topics["operational_alerts"])
        )
        
        self.alarms[f"{queue_name}_depth"] = queue_depth_alarm
        
        # Add SQS widget to dashboard
        sqs_widget = cloudwatch.GraphWidget(
            title=f"SQS {queue_name} - Message Count",
            left=[
                queue.metric_approximate_number_of_messages_visible()
            ],
            width=12,
            height=6
        )
        
        self.dashboard.add_widgets(sqs_widget)

    def add_s3_monitoring(self, bucket_name: str, bucket) -> None:
        """Add monitoring for S3 buckets"""
        # Create custom metrics for S3 object counts and sizes
        s3_objects_widget = cloudwatch.GraphWidget(
            title=f"S3 {bucket_name} - Storage Metrics",
            left=[
                cloudwatch.Metric(
                    namespace="AWS/S3",
                    metric_name="BucketSizeBytes",
                    dimensions_map={
                        "BucketName": bucket.bucket_name,
                        "StorageType": "StandardStorage"
                    },
                    period=Duration.hours(24),
                    statistic="Average"
                ),
                cloudwatch.Metric(
                    namespace="AWS/S3",
                    metric_name="NumberOfObjects",
                    dimensions_map={
                        "BucketName": bucket.bucket_name,
                        "StorageType": "AllStorageTypes"
                    },
                    period=Duration.hours(24),
                    statistic="Average"
                )
            ],
            width=12,
            height=6
        )
        
        self.dashboard.add_widgets(s3_objects_widget)
    
    def add_log_group_monitoring(self, log_group_name: str, log_group) -> None:
        """Add monitoring for CloudWatch log groups"""
        # Log group error alarm
        log_error_alarm = cloudwatch.Alarm(
            self, f"{log_group_name}LogErrorAlarm",
            alarm_name=f"bedrock-budgeteer-{self.environment_name}-{log_group_name}-log-errors",
            alarm_description=f"Log errors in {log_group_name} log group",
            metric=cloudwatch.Metric(
                namespace="AWS/Logs",
                metric_name="ErrorCount",
                dimensions_map={"LogGroupName": log_group.log_group_name},
                period=Duration.minutes(5),
                statistic="Sum"
            ),
            threshold=1,
            evaluation_periods=1,
            comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
            treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING
        )
        
        log_error_alarm.add_alarm_action(
            cloudwatch_actions.SnsAction(self.topics["operational_alerts"])
        )
        
        self.alarms[f"{log_group_name}_log_errors"] = log_error_alarm
    
    def add_stepfunctions_monitoring(self, state_machine_name: str, state_machine) -> None:
        """Add monitoring for Step Functions state machines"""
        
        # Execution failure alarm
        execution_failure_alarm = cloudwatch.Alarm(
            self, f"{state_machine_name}ExecutionFailureAlarm",
            alarm_name=f"bedrock-budgeteer-{self.environment_name}-{state_machine_name}-execution-failures",
            alarm_description=f"Step Functions execution failures for {state_machine_name}",
            metric=cloudwatch.Metric(
                namespace="AWS/States",
                metric_name="ExecutionsFailed",
                dimensions_map={"StateMachineArn": state_machine.state_machine_arn},
                period=Duration.minutes(5),
                statistic="Sum"
            ),
            threshold=1,
            evaluation_periods=1,
            comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
            treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING
        )
        
        execution_failure_alarm.add_alarm_action(
            cloudwatch_actions.SnsAction(self.topics["high_severity"])
        )
        
        self.alarms[f"{state_machine_name}_execution_failures"] = execution_failure_alarm
        
        # Execution timeout alarm
        execution_timeout_alarm = cloudwatch.Alarm(
            self, f"{state_machine_name}ExecutionTimeoutAlarm",
            alarm_name=f"bedrock-budgeteer-{self.environment_name}-{state_machine_name}-execution-timeouts",
            alarm_description=f"Step Functions execution timeouts for {state_machine_name}",
            metric=cloudwatch.Metric(
                namespace="AWS/States",
                metric_name="ExecutionTime",
                dimensions_map={"StateMachineArn": state_machine.state_machine_arn},
                period=Duration.minutes(5),
                statistic="Maximum"
            ),
            threshold=900,  # 15 minutes
            evaluation_periods=2,
            comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_THRESHOLD,
            treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING
        )
        
        execution_timeout_alarm.add_alarm_action(
            cloudwatch_actions.SnsAction(self.topics["operational_alerts"])
        )
        
        self.alarms[f"{state_machine_name}_execution_timeouts"] = execution_timeout_alarm
        
        # Execution throttling alarm
        execution_throttle_alarm = cloudwatch.Alarm(
            self, f"{state_machine_name}ExecutionThrottleAlarm",
            alarm_name=f"bedrock-budgeteer-{self.environment_name}-{state_machine_name}-execution-throttled",
            alarm_description=f"Step Functions execution throttling for {state_machine_name}",
            metric=cloudwatch.Metric(
                namespace="AWS/States",
                metric_name="ExecutionThrottled",
                dimensions_map={"StateMachineArn": state_machine.state_machine_arn},
                period=Duration.minutes(5),
                statistic="Sum"
            ),
            threshold=5,
            evaluation_periods=2,
            comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
            treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING
        )
        
        execution_throttle_alarm.add_alarm_action(
            cloudwatch_actions.SnsAction(self.topics["operational_alerts"])
        )
        
        self.alarms[f"{state_machine_name}_execution_throttled"] = execution_throttle_alarm
        
        # Add Step Functions widgets to dashboard
        stepfunctions_executions_widget = cloudwatch.GraphWidget(
            title=f"Step Functions {state_machine_name} - Executions",
            left=[
                cloudwatch.Metric(
                    namespace="AWS/States",
                    metric_name="ExecutionsStarted",
                    dimensions_map={"StateMachineArn": state_machine.state_machine_arn},
                    period=Duration.minutes(5),
                    statistic="Sum",
                    label="Started"
                ),
                cloudwatch.Metric(
                    namespace="AWS/States",
                    metric_name="ExecutionsSucceeded",
                    dimensions_map={"StateMachineArn": state_machine.state_machine_arn},
                    period=Duration.minutes(5),
                    statistic="Sum",
                    label="Succeeded"
                ),
                cloudwatch.Metric(
                    namespace="AWS/States",
                    metric_name="ExecutionsFailed",
                    dimensions_map={"StateMachineArn": state_machine.state_machine_arn},
                    period=Duration.minutes(5),
                    statistic="Sum",
                    label="Failed"
                )
            ],
            width=12,
            height=6
        )
        
        stepfunctions_performance_widget = cloudwatch.GraphWidget(
            title=f"Step Functions {state_machine_name} - Performance",
            left=[
                cloudwatch.Metric(
                    namespace="AWS/States",
                    metric_name="ExecutionTime",
                    dimensions_map={"StateMachineArn": state_machine.state_machine_arn},
                    period=Duration.minutes(5),
                    statistic="Average",
                    label="Avg Execution Time"
                )
            ],
            right=[
                cloudwatch.Metric(
                    namespace="AWS/States",
                    metric_name="ExecutionThrottled",
                    dimensions_map={"StateMachineArn": state_machine.state_machine_arn},
                    period=Duration.minutes(5),
                    statistic="Sum",
                    label="Throttled"
                )
            ],
            width=12,
            height=6
        )
        
        self.dashboard.add_widgets(stepfunctions_executions_widget, stepfunctions_performance_widget)
    
    def create_workflow_dashboard(self) -> None:
        """Create a dedicated dashboard for workflow orchestration"""
        self.workflow_dashboard = cloudwatch.Dashboard(
            self, "WorkflowDashboard",
            dashboard_name=f"bedrock-budgeteer-{self.environment_name}-workflow-orchestration"
        )
        
        # Add header
        self.workflow_dashboard.add_widgets(
            cloudwatch.TextWidget(
                markdown=f"# Workflow Orchestration - {self.environment_name.upper()}\n\nMonitoring for suspension and restoration workflows powered by Step Functions",
                width=24,
                height=2
            )
        )
        
        # Workflow summary widget
        workflow_summary_widget = cloudwatch.GraphWidget(
            title="Workflow Summary - Last 24 Hours",
            left=[
                cloudwatch.Metric(
                    namespace="BedrockBudgeteer",
                    metric_name="WorkflowsStarted",
                    dimensions_map={"Environment": self.environment_name},
                    period=Duration.hours(1),
                    statistic="Sum",
                    label="Total Workflows Started"
                ),
                cloudwatch.Metric(
                    namespace="BedrockBudgeteer",
                    metric_name="SuspensionWorkflowsCompleted",
                    dimensions_map={"Environment": self.environment_name},
                    period=Duration.hours(1),
                    statistic="Sum",
                    label="Suspensions Completed"
                ),
                cloudwatch.Metric(
                    namespace="BedrockBudgeteer",
                    metric_name="RestorationWorkflowsCompleted",
                    dimensions_map={"Environment": self.environment_name},
                    period=Duration.hours(1),
                    statistic="Sum",
                    label="Restorations Completed"
                )
            ],
            width=24,
            height=6
        )
        
        self.workflow_dashboard.add_widgets(workflow_summary_widget)
    
    def create_ingestion_pipeline_dashboard(self) -> None:
        """Create a dedicated dashboard for the ingestion pipeline"""
        self.ingestion_dashboard = cloudwatch.Dashboard(
            self, "IngestionPipelineDashboard",
            dashboard_name=f"bedrock-budgeteer-{self.environment_name}-ingestion-pipeline"
        )
        
        # Add header
        self.ingestion_dashboard.add_widgets(
            cloudwatch.TextWidget(
                markdown=f"# Event Ingestion Pipeline - {self.environment_name.upper()}\n\nReal-time monitoring of CloudTrail → EventBridge → Firehose → S3 pipeline",
                width=24,
                height=2
            )
        )
    
    def add_email_subscription(self, topic_name: str, email: str) -> None:
        """Add email subscription to SNS topic"""
        if topic_name in self.topics:
            self.topics[topic_name].add_subscription(
                sns_subs.EmailSubscription(email)
            )
    
    def add_slack_subscription(self, topic_name: str, webhook_url: str) -> None:
        """Add Slack webhook subscription to SNS topic"""
        if topic_name in self.topics:
            # Create Lambda function for Slack integration
            slack_function = self._create_slack_notification_lambda(webhook_url)
            
            # Subscribe Lambda to SNS topic
            self.topics[topic_name].add_subscription(
                sns_subs.LambdaSubscription(slack_function)
            )
    
    
    def add_webhook_subscription(self, topic_name: str, webhook_url: str, headers: Optional[Dict[str, str]] = None) -> None:
        """Add generic webhook subscription to SNS topic"""
        if topic_name in self.topics:
            # Create Lambda function for webhook integration
            webhook_function = self._create_webhook_notification_lambda(webhook_url, headers or {})
            
            # Subscribe Lambda to SNS topic
            self.topics[topic_name].add_subscription(
                sns_subs.LambdaSubscription(webhook_function)
            )
    
    def add_sms_subscription(self, topic_name: str, phone_number: str) -> None:
        """Add SMS subscription to SNS topic for critical alerts"""
        if topic_name in self.topics:
            self.topics[topic_name].add_subscription(
                sns_subs.SmsSubscription(phone_number)
            )
    
    def create_custom_business_metrics(self) -> None:
        """Create custom CloudWatch metrics for business monitoring"""
        # Business metrics namespace
        self.business_metrics_namespace = "BedrockBudgeteer"
        
        # Create custom metric alarms for business KPIs
        self._create_budget_threshold_alarms()
        self._create_user_activity_alarms()
        self._create_suspension_alarms()
        self._create_cost_optimization_alarms()
        
        # Add business metrics dashboard
        self._create_business_dashboard()
    
    def _create_budget_threshold_alarms(self) -> None:
        """Create alarms for budget threshold violations"""
        # High number of warning threshold violations
        warning_violations_alarm = cloudwatch.Alarm(
            self, "BudgetWarningViolationsAlarm",
            alarm_name=f"bedrock-budgeteer-{self.environment_name}-budget-warning-violations",
            alarm_description="High number of budget warning threshold violations",
            metric=cloudwatch.Metric(
                namespace=self.business_metrics_namespace,
                metric_name="BudgetWarningViolations",
                dimensions_map={"Environment": self.environment_name},
                period=Duration.minutes(15),
                statistic="Sum"
            ),
            threshold=10,  # More than 10 warning violations in 15 minutes
            evaluation_periods=1,
            comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
            treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING
        )
        
        warning_violations_alarm.add_alarm_action(
            cloudwatch_actions.SnsAction(self.topics["budget_alerts"])
        )
        
        self.alarms["budget_warning_violations"] = warning_violations_alarm
        
        # Budget exceeded events
        budget_exceeded_alarm = cloudwatch.Alarm(
            self, "BudgetExceededAlarm",
            alarm_name=f"bedrock-budgeteer-{self.environment_name}-budget-exceeded",
            alarm_description="Budget exceeded events requiring immediate attention",
            metric=cloudwatch.Metric(
                namespace=self.business_metrics_namespace,
                metric_name="BudgetExceeded",
                dimensions_map={"Environment": self.environment_name},
                period=Duration.minutes(5),
                statistic="Sum"
            ),
            threshold=1,  # Any budget exceeded event
            evaluation_periods=1,
            comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
            treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING
        )
        
        budget_exceeded_alarm.add_alarm_action(
            cloudwatch_actions.SnsAction(self.topics["high_severity"])
        )
        
        self.alarms["budget_exceeded"] = budget_exceeded_alarm
    
    def _create_user_activity_alarms(self) -> None:
        """Create alarms for user activity monitoring"""
        # Low user activity alarm
        low_activity_alarm = cloudwatch.Alarm(
            self, "LowUserActivityAlarm",
            alarm_name=f"bedrock-budgeteer-{self.environment_name}-low-user-activity",
            alarm_description="Unusually low user activity detected",
            metric=cloudwatch.Metric(
                namespace=self.business_metrics_namespace,
                metric_name="ActiveUsers",
                dimensions_map={"Environment": self.environment_name},
                period=Duration.hours(1),
                statistic="Average"
            ),
            threshold=1,  # Less than 1 active user per hour
            evaluation_periods=3,
            comparison_operator=cloudwatch.ComparisonOperator.LESS_THAN_THRESHOLD,
            treat_missing_data=cloudwatch.TreatMissingData.BREACHING
        )
        
        low_activity_alarm.add_alarm_action(
            cloudwatch_actions.SnsAction(self.topics["operational_alerts"])
        )
        
        self.alarms["low_user_activity"] = low_activity_alarm
        
        # High new user registration alarm
        high_registration_alarm = cloudwatch.Alarm(
            self, "HighUserRegistrationAlarm",
            alarm_name=f"bedrock-budgeteer-{self.environment_name}-high-user-registration",
            alarm_description="Unusually high user registration rate",
            metric=cloudwatch.Metric(
                namespace=self.business_metrics_namespace,
                metric_name="NewUserRegistrations",
                dimensions_map={"Environment": self.environment_name},
                period=Duration.hours(1),
                statistic="Sum"
            ),
            threshold=50,  # More than 50 new users per hour
            evaluation_periods=1,
            comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
            treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING
        )
        
        high_registration_alarm.add_alarm_action(
            cloudwatch_actions.SnsAction(self.topics["operational_alerts"])
        )
        
        self.alarms["high_user_registration"] = high_registration_alarm
    
    def _create_suspension_alarms(self) -> None:
        """Create alarms for suspension and restoration monitoring"""
        # High suspension rate alarm
        high_suspension_alarm = cloudwatch.Alarm(
            self, "HighSuspensionRateAlarm",
            alarm_name=f"bedrock-budgeteer-{self.environment_name}-high-suspension-rate",
            alarm_description="High rate of user suspensions",
            metric=cloudwatch.Metric(
                namespace=self.business_metrics_namespace,
                metric_name="UserSuspensions",
                dimensions_map={"Environment": self.environment_name},
                period=Duration.hours(1),
                statistic="Sum"
            ),
            threshold=10,  # More than 10 suspensions per hour
            evaluation_periods=1,
            comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
            treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING
        )
        
        high_suspension_alarm.add_alarm_action(
            cloudwatch_actions.SnsAction(self.topics["high_severity"])
        )
        
        self.alarms["high_suspension_rate"] = high_suspension_alarm
        
        # Failed suspension alarm
        failed_suspension_alarm = cloudwatch.Alarm(
            self, "FailedSuspensionAlarm",
            alarm_name=f"bedrock-budgeteer-{self.environment_name}-failed-suspensions",
            alarm_description="Failed suspension workflows",
            metric=cloudwatch.Metric(
                namespace=self.business_metrics_namespace,
                metric_name="FailedSuspensions",
                dimensions_map={"Environment": self.environment_name},
                period=Duration.minutes(5),
                statistic="Sum"
            ),
            threshold=1,  # Any failed suspension
            evaluation_periods=1,
            comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
            treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING
        )
        
        failed_suspension_alarm.add_alarm_action(
            cloudwatch_actions.SnsAction(self.topics["high_severity"])
        )
        
        self.alarms["failed_suspensions"] = failed_suspension_alarm
    
    def _create_cost_optimization_alarms(self) -> None:
        """Create alarms for cost optimization monitoring"""
        # System operational cost alarm
        high_operational_cost_alarm = cloudwatch.Alarm(
            self, "HighOperationalCostAlarm",
            alarm_name=f"bedrock-budgeteer-{self.environment_name}-high-operational-cost",
            alarm_description="High operational costs for Bedrock Budgeteer system",
            metric=cloudwatch.Metric(
                namespace=self.business_metrics_namespace,
                metric_name="SystemOperationalCost",
                dimensions_map={"Environment": self.environment_name},
                period=Duration.hours(24),
                statistic="Sum"
            ),
            threshold=100.0,  # More than $100 per day
            evaluation_periods=1,
            comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
            treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING
        )
        
        high_operational_cost_alarm.add_alarm_action(
            cloudwatch_actions.SnsAction(self.topics["budget_alerts"])
        )
        
        self.alarms["high_operational_cost"] = high_operational_cost_alarm
    
    def _create_business_dashboard(self) -> None:
        """Create dedicated dashboard for business metrics"""
        self.business_dashboard = cloudwatch.Dashboard(
            self, "BusinessDashboard",
            dashboard_name=f"bedrock-budgeteer-{self.environment_name}-business-metrics"
        )
        
        # Add header
        self.business_dashboard.add_widgets(
            cloudwatch.TextWidget(
                markdown=f"# Business Metrics - {self.environment_name.upper()}\n\nKey business indicators and operational metrics for Bedrock Budgeteer",
                width=24,
                height=2
            )
        )
        
        # Budget threshold violations widget
        budget_violations_widget = cloudwatch.GraphWidget(
            title="Budget Threshold Violations",
            left=[
                cloudwatch.Metric(
                    namespace=self.business_metrics_namespace,
                    metric_name="BudgetWarningViolations",
                    dimensions_map={"Environment": self.environment_name},
                    period=Duration.hours(1),
                    statistic="Sum",
                    label="Warning Violations"
                ),
                cloudwatch.Metric(
                    namespace=self.business_metrics_namespace,
                    metric_name="BudgetCriticalViolations",
                    dimensions_map={"Environment": self.environment_name},
                    period=Duration.hours(1),
                    statistic="Sum",
                    label="Critical Violations"
                ),
                cloudwatch.Metric(
                    namespace=self.business_metrics_namespace,
                    metric_name="BudgetExceeded",
                    dimensions_map={"Environment": self.environment_name},
                    period=Duration.hours(1),
                    statistic="Sum",
                    label="Budget Exceeded"
                )
            ],
            width=12,
            height=6
        )
        
        # User activity widget
        user_activity_widget = cloudwatch.GraphWidget(
            title="User Activity",
            left=[
                cloudwatch.Metric(
                    namespace=self.business_metrics_namespace,
                    metric_name="ActiveUsers",
                    dimensions_map={"Environment": self.environment_name},
                    period=Duration.hours(1),
                    statistic="Average",
                    label="Active Users"
                ),
                cloudwatch.Metric(
                    namespace=self.business_metrics_namespace,
                    metric_name="NewUserRegistrations",
                    dimensions_map={"Environment": self.environment_name},
                    period=Duration.hours(1),
                    statistic="Sum",
                    label="New Registrations"
                )
            ],
            width=12,
            height=6
        )
        
        # Suspension and restoration widget
        suspension_widget = cloudwatch.GraphWidget(
            title="Suspension & Restoration Activity",
            left=[
                cloudwatch.Metric(
                    namespace=self.business_metrics_namespace,
                    metric_name="UserSuspensions",
                    dimensions_map={"Environment": self.environment_name},
                    period=Duration.hours(1),
                    statistic="Sum",
                    label="Suspensions"
                ),
                cloudwatch.Metric(
                    namespace=self.business_metrics_namespace,
                    metric_name="UserRestorations",
                    dimensions_map={"Environment": self.environment_name},
                    period=Duration.hours(1),
                    statistic="Sum",
                    label="Restorations"
                )
            ],
            right=[
                cloudwatch.Metric(
                    namespace=self.business_metrics_namespace,
                    metric_name="FailedSuspensions",
                    dimensions_map={"Environment": self.environment_name},
                    period=Duration.hours(1),
                    statistic="Sum",
                    label="Failed Suspensions"
                ),
                cloudwatch.Metric(
                    namespace=self.business_metrics_namespace,
                    metric_name="FailedRestorations",
                    dimensions_map={"Environment": self.environment_name},
                    period=Duration.hours(1),
                    statistic="Sum",
                    label="Failed Restorations"
                )
            ],
            width=12,
            height=6
        )
        
        # Cost metrics widget
        cost_widget = cloudwatch.GraphWidget(
            title="System Operational Costs",
            left=[
                cloudwatch.Metric(
                    namespace=self.business_metrics_namespace,
                    metric_name="SystemOperationalCost",
                    dimensions_map={"Environment": self.environment_name},
                    period=Duration.hours(24),
                    statistic="Sum",
                    label="Daily Operational Cost (USD)"
                )
            ],
            width=24,
            height=6
        )
        
        self.business_dashboard.add_widgets(
            budget_violations_widget, user_activity_widget,
            suspension_widget, cost_widget
        )
    
    def _create_slack_notification_lambda(self, webhook_url: str):
        """Create Lambda function for Slack notifications"""
        from aws_cdk import aws_lambda as lambda_
        
        slack_function = lambda_.Function(
            self, "SlackNotificationFunction",
            function_name=f"bedrock-budgeteer-{self.environment_name}-slack-notifications",
            runtime=lambda_.Runtime.PYTHON_3_9,
            handler="index.handler",
            code=lambda_.Code.from_inline(f"""
import json
import urllib3
import boto3

def handler(event, context):
    webhook_url = "{webhook_url}"
    
    # Parse SNS message
    for record in event['Records']:
        sns_message = json.loads(record['Sns']['Message'])
        subject = record['Sns']['Subject']
        
        # Format Slack message
        slack_message = {{
            "text": f"🚨 Bedrock Budgeteer Alert",
            "attachments": [{{
                "color": "danger" if "high-severity" in record['Sns']['TopicArn'] else "warning",
                "title": subject,
                "text": sns_message,
                "footer": "Bedrock Budgeteer",
                "ts": int(context.aws_request_id)
            }}]
        }}
        
        # Send to Slack
        http = urllib3.PoolManager()
        response = http.request(
            'POST',
            webhook_url,
            body=json.dumps(slack_message),
            headers={{'Content-Type': 'application/json'}}
        )
        
        print(f"Slack notification sent: {{response.status}}")
    
    return {{'statusCode': 200}}
"""),
            timeout=Duration.seconds(30),
        )
        
        # Grant SNS invoke permissions
        slack_function.add_permission(
            "SNSInvokePermission",
            principal=iam.ServicePrincipal("sns.amazonaws.com"),
            action="lambda:InvokeFunction"
        )
        
        return slack_function
    
    
    def _create_webhook_notification_lambda(self, webhook_url: str, headers: Dict[str, str]):
        """Create Lambda function for generic webhook notifications"""
        from aws_cdk import aws_lambda as lambda_
        import json as json_module
        
        webhook_function = lambda_.Function(
            self, "WebhookNotificationFunction",
            function_name=f"bedrock-budgeteer-{self.environment_name}-webhook-notifications",
            runtime=lambda_.Runtime.PYTHON_3_9,
            handler="index.handler",
            code=lambda_.Code.from_inline(f"""
import json
import urllib3
from datetime import datetime

def handler(event, context):
    webhook_url = "{webhook_url}"
    custom_headers = {json_module.dumps(headers)}
    
    # Parse SNS message
    for record in event['Records']:
        sns_message = json.loads(record['Sns']['Message'])
        subject = record['Sns']['Subject']
        
        # Create webhook payload
        webhook_payload = {{
            "timestamp": datetime.utcnow().isoformat(),
            "source": "bedrock-budgeteer",
            "environment": "{self.environment_name}",
            "alert": {{
                "subject": subject,
                "message": sns_message,
                "severity": "critical" if "high-severity" in record['Sns']['TopicArn'] else "warning",
                "topic_arn": record['Sns']['TopicArn']
            }}
        }}
        
        # Prepare headers
        request_headers = {{'Content-Type': 'application/json'}}
        request_headers.update(custom_headers)
        
        # Send webhook
        http = urllib3.PoolManager()
        response = http.request(
            'POST',
            webhook_url,
            body=json.dumps(webhook_payload),
            headers=request_headers
        )
        
        print(f"Webhook notification sent: {{response.status}}")
    
    return {{'statusCode': 200}}
"""),
            timeout=Duration.seconds(30),
        )
        
        # Grant SNS invoke permissions
        webhook_function.add_permission(
            "SNSInvokePermission",
            principal=iam.ServicePrincipal("sns.amazonaws.com"),
            action="lambda:InvokeFunction"
        )
        
        return webhook_function
    

