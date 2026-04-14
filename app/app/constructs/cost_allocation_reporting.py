"""
Cost Allocation Reporting Construct for Bedrock Budgeteer
Creates Lambda functions for daily Cost Explorer sync and cost reconciliation,
with EventBridge schedules and CloudWatch dashboard widgets.
"""
from typing import Dict, Optional
from aws_cdk import (
    Duration,
    RemovalPolicy,
    aws_lambda as lambda_,
    aws_events as events,
    aws_events_targets as targets,
    aws_iam as iam,
    aws_sqs as sqs,
    aws_kms as kms,
    aws_sns as sns,
    aws_dynamodb as dynamodb,
)
from constructs import Construct

from .lambda_functions.cost_allocation_sync import get_cost_allocation_sync_function_code
from .lambda_functions.cost_reconciliation import get_cost_reconciliation_function_code


class CostAllocationReportingConstruct(Construct):
    """Construct for Cost Explorer sync and reconciliation reporting"""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        environment_name: str,
        lambda_execution_role: iam.Role,
        usage_tracking_table: dynamodb.Table,
        sns_topics: Optional[Dict[str, sns.Topic]] = None,
        kms_key: Optional[kms.Key] = None,
        **kwargs
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.environment_name = environment_name
        self.lambda_execution_role = lambda_execution_role
        self.usage_tracking_table = usage_tracking_table
        self.sns_topics = sns_topics or {}
        self.kms_key = kms_key

        self.functions: Dict[str, lambda_.Function] = {}
        self.dlq_queues: Dict[str, sqs.Queue] = {}

        self._create_dlqs()
        self._create_lambda_functions()
        self._create_eventbridge_schedules()

    def _create_dlqs(self) -> None:
        """Create dead letter queues for reporting Lambda functions"""
        for name in ["cost_allocation_sync", "cost_reconciliation"]:
            dlq_name = f"bedrock-budgeteer-{self.environment_name}-{name.replace('_', '-')}-dlq"
            self.dlq_queues[name] = sqs.Queue(
                self, f"{name.title().replace('_', '')}DLQ",
                queue_name=dlq_name,
                retention_period=Duration.days(14),
                visibility_timeout=Duration.minutes(30),  # 6x Lambda timeout per AWS best practice
                encryption=sqs.QueueEncryption.KMS_MANAGED,
                removal_policy=RemovalPolicy.DESTROY
            )

    def _create_lambda_functions(self) -> None:
        """Create reporting Lambda functions with inline code"""
        common_config = {
            "runtime": lambda_.Runtime.PYTHON_3_12,
            "timeout": Duration.minutes(5),
            "memory_size": 256,
            "role": self.lambda_execution_role,
        }

        # Cost Allocation Sync Lambda
        self.functions["cost_allocation_sync"] = lambda_.Function(
            self, "CostAllocationSyncFunction",
            function_name=f"bedrock-budgeteer-cost-allocation-sync-{self.environment_name}",
            code=lambda_.Code.from_inline(get_cost_allocation_sync_function_code()),
            handler="index.lambda_handler",
            dead_letter_queue=self.dlq_queues["cost_allocation_sync"],
            environment={
                "ENVIRONMENT": self.environment_name,
            },
            **common_config
        )

        # Cost Reconciliation Lambda
        reconciliation_env = {
            "ENVIRONMENT": self.environment_name,
            "USAGE_TRACKING_TABLE": self.usage_tracking_table.table_name,
        }

        operational_topic = self.sns_topics.get("operational_alerts")
        if operational_topic:
            reconciliation_env["OPERATIONAL_ALERTS_SNS_TOPIC_ARN"] = operational_topic.topic_arn

        self.functions["cost_reconciliation"] = lambda_.Function(
            self, "CostReconciliationFunction",
            function_name=f"bedrock-budgeteer-cost-reconciliation-{self.environment_name}",
            code=lambda_.Code.from_inline(get_cost_reconciliation_function_code()),
            handler="index.lambda_handler",
            dead_letter_queue=self.dlq_queues["cost_reconciliation"],
            environment=reconciliation_env,
            **common_config
        )

    def _create_eventbridge_schedules(self) -> None:
        """Create daily EventBridge schedules for reporting"""
        # Daily sync at 06:00 UTC (after Cost Explorer data refreshes)
        sync_rule = events.Rule(
            self, "CostAllocationSyncSchedule",
            rule_name=f"bedrock-budgeteer-{self.environment_name}-cost-sync-daily",
            description="Daily Cost Explorer sync for Bedrock cost allocation",
            schedule=events.Schedule.cron(hour="6", minute="0"),
            enabled=True
        )
        sync_rule.add_target(
            targets.LambdaFunction(self.functions["cost_allocation_sync"])
        )

        # Daily reconciliation at 07:00 UTC (1 hour after sync)
        reconciliation_rule = events.Rule(
            self, "CostReconciliationSchedule",
            rule_name=f"bedrock-budgeteer-{self.environment_name}-cost-reconciliation-daily",
            description="Daily cost reconciliation between Cost Explorer and internal tracking",
            schedule=events.Schedule.cron(hour="7", minute="0"),
            enabled=True
        )
        reconciliation_rule.add_target(
            targets.LambdaFunction(self.functions["cost_reconciliation"])
        )
