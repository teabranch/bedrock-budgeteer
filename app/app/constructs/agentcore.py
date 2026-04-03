"""
AgentCore Construct for Bedrock Budgeteer
Manages AgentCore runtime budget monitoring and enforcement.
Creates DynamoDB table, Lambda functions, EventBridge rules, and Step Functions.
"""
from typing import Dict, Optional
from aws_cdk import (
    Duration,
    RemovalPolicy,
    aws_dynamodb as dynamodb,
    aws_lambda as lambda_,
    aws_events as events,
    aws_events_targets as targets,
    aws_iam as iam,
    aws_sqs as sqs,
    aws_kms as kms,
    aws_sns as sns,
    aws_stepfunctions as sfn,
    aws_stepfunctions_tasks as tasks,
)
from constructs import Construct

from .lambda_functions.agentcore_setup import get_agentcore_setup_function_code
from .lambda_functions.agentcore_budget_monitor import get_agentcore_budget_monitor_function_code
from .lambda_functions.agentcore_budget_manager import get_agentcore_budget_manager_function_code
from .shared.lambda_utilities import get_shared_lambda_utilities
from .shared.agentcore_helpers import get_agentcore_helpers
from .workflow_lambda_functions.agentcore_iam_utilities import get_agentcore_iam_utilities_function_code


class AgentCoreConstruct(Construct):
    """Construct for AgentCore runtime budget monitoring and enforcement"""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        environment_name: str,
        lambda_execution_role: iam.Role,
        step_functions_role: iam.Role,
        usage_tracking_table: dynamodb.Table,
        sns_topics: Optional[Dict[str, sns.Topic]] = None,
        kms_key: Optional[kms.Key] = None,
        **kwargs
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.environment_name = environment_name
        self.lambda_execution_role = lambda_execution_role
        self.step_functions_role = step_functions_role
        self.usage_tracking_table = usage_tracking_table
        self.sns_topics = sns_topics or {}
        self.kms_key = kms_key

        self.functions: Dict[str, lambda_.Function] = {}
        self.dlq_queues: Dict[str, sqs.Queue] = {}

        # Create resources
        self._create_dynamodb_table()
        self._create_dlqs()
        self._create_lambda_functions()
        self._create_eventbridge_rules()
        self._create_step_functions()

    def _create_dynamodb_table(self) -> None:
        """Create the agentcore-budgets DynamoDB table with role_arn GSI"""
        encryption_props = {}
        if self.kms_key:
            encryption_props = {
                "encryption": dynamodb.TableEncryption.CUSTOMER_MANAGED,
                "encryption_key": self.kms_key
            }
        else:
            encryption_props = {
                "encryption": dynamodb.TableEncryption.AWS_MANAGED
            }

        self.agentcore_budgets_table = dynamodb.Table(
            self, "AgentCoreBudgetsTable",
            table_name=f"bedrock-budgeteer-{self.environment_name}-agentcore-budgets",
            partition_key=dynamodb.Attribute(
                name="runtime_id",
                type=dynamodb.AttributeType.STRING
            ),
            billing_mode=dynamodb.BillingMode.PROVISIONED,
            read_capacity=5,
            write_capacity=5,
            removal_policy=RemovalPolicy.DESTROY,
            point_in_time_recovery_specification=dynamodb.PointInTimeRecoverySpecification(
                point_in_time_recovery_enabled=False
            ),
            **encryption_props
        )

        # Add GSI for role_arn lookups
        self.agentcore_budgets_table.add_global_secondary_index(
            index_name="role_arn-index",
            partition_key=dynamodb.Attribute(
                name="role_arn",
                type=dynamodb.AttributeType.STRING
            ),
            projection_type=dynamodb.ProjectionType.ALL,
            read_capacity=5,
            write_capacity=5
        )

    def _create_dlqs(self) -> None:
        """Create dead letter queues for AgentCore Lambda functions"""
        for name in ["agentcore_setup", "agentcore_budget_monitor",
                      "agentcore_budget_manager", "agentcore_iam_utilities"]:
            dlq_name = f"bedrock-budgeteer-{self.environment_name}-{name.replace('_', '-')}-dlq"
            self.dlq_queues[name] = sqs.Queue(
                self, f"{name.title().replace('_', '')}DLQ",
                queue_name=dlq_name,
                retention_period=Duration.days(14),
                visibility_timeout=Duration.minutes(5),
                encryption=sqs.QueueEncryption.KMS_MANAGED,
                removal_policy=RemovalPolicy.DESTROY
            )

    def _create_lambda_functions(self) -> None:
        """Create AgentCore Lambda functions with inline code"""
        common_config = {
            "runtime": lambda_.Runtime.PYTHON_3_12,
            "timeout": Duration.minutes(5),
            "memory_size": 256,
            "role": self.lambda_execution_role,
        }

        common_env = {
            "AGENTCORE_BUDGETS_TABLE": self.agentcore_budgets_table.table_name,
            "USAGE_TRACKING_TABLE": self.usage_tracking_table.table_name,
            "ENVIRONMENT": self.environment_name,
        }

        # AgentCore Setup
        setup_code = f"""
{get_shared_lambda_utilities()}

{get_agentcore_setup_function_code()}
"""
        self.functions["agentcore_setup"] = lambda_.Function(
            self, "AgentCoreSetupFunction",
            function_name=f"bedrock-budgeteer-agentcore-setup-{self.environment_name}",
            code=lambda_.Code.from_inline(setup_code),
            handler="index.lambda_handler",
            dead_letter_queue=self.dlq_queues["agentcore_setup"],
            environment=common_env,
            **common_config
        )

        # AgentCore Budget Monitor
        monitor_code = f"""
{get_shared_lambda_utilities()}

{get_agentcore_budget_monitor_function_code()}
"""
        self.functions["agentcore_budget_monitor"] = lambda_.Function(
            self, "AgentCoreBudgetMonitorFunction",
            function_name=f"bedrock-budgeteer-agentcore-budget-monitor-{self.environment_name}",
            code=lambda_.Code.from_inline(monitor_code),
            handler="index.lambda_handler",
            dead_letter_queue=self.dlq_queues["agentcore_budget_monitor"],
            environment=common_env,
            **common_config
        )

        # AgentCore Budget Manager (with Function URL)
        manager_code = f"""
{get_shared_lambda_utilities()}

{get_agentcore_budget_manager_function_code()}
"""
        self.functions["agentcore_budget_manager"] = lambda_.Function(
            self, "AgentCoreBudgetManagerFunction",
            function_name=f"bedrock-budgeteer-agentcore-budget-manager-{self.environment_name}",
            code=lambda_.Code.from_inline(manager_code),
            handler="index.lambda_handler",
            dead_letter_queue=self.dlq_queues["agentcore_budget_manager"],
            environment=common_env,
            **common_config
        )

        # Add Function URL with IAM auth
        self.budget_manager_url = self.functions["agentcore_budget_manager"].add_function_url(
            auth_type=lambda_.FunctionUrlAuthType.AWS_IAM
        )

        # AgentCore IAM Utilities (workflow function)
        iam_code = f"""
{get_agentcore_iam_utilities_function_code()}
"""
        self.functions["agentcore_iam_utilities"] = lambda_.Function(
            self, "AgentCoreIamUtilitiesFunction",
            function_name=f"bedrock-budgeteer-agentcore-iam-utilities-{self.environment_name}",
            code=lambda_.Code.from_inline(iam_code),
            handler="index.lambda_handler",
            dead_letter_queue=self.dlq_queues["agentcore_iam_utilities"],
            environment=common_env,
            **common_config
        )

    def _create_eventbridge_rules(self) -> None:
        """Create EventBridge rules for AgentCore lifecycle events"""
        # Lifecycle events rule
        self.lifecycle_rule = events.Rule(
            self, "AgentCoreLifecycleRule",
            rule_name=f"bedrock-budgeteer-{self.environment_name}-agentcore-lifecycle",
            description="Capture AgentCore runtime lifecycle events",
            event_pattern=events.EventPattern(
                source=["aws.bedrock-agentcore"],
                detail={
                    "eventSource": ["bedrock-agentcore.amazonaws.com"],
                    "eventName": ["CreateAgentRuntime", "UpdateAgentRuntime", "DeleteAgentRuntime"]
                }
            )
        )
        self.lifecycle_rule.add_target(
            targets.LambdaFunction(self.functions["agentcore_setup"])
        )

        # Budget monitor schedule (every 5 minutes)
        self.monitor_schedule = events.Rule(
            self, "AgentCoreBudgetMonitorSchedule",
            rule_name=f"bedrock-budgeteer-{self.environment_name}-agentcore-budget-monitor",
            description="Run AgentCore budget monitor every 5 minutes",
            schedule=events.Schedule.rate(Duration.minutes(5))
        )
        self.monitor_schedule.add_target(
            targets.LambdaFunction(self.functions["agentcore_budget_monitor"])
        )

    def _create_step_functions(self) -> None:
        """Create suspension and restoration Step Function state machines"""
        # --- Suspension Workflow ---
        send_grace = tasks.LambdaInvoke(
            self, "ACGraceNotification",
            lambda_function=self.functions["agentcore_iam_utilities"],
            payload=sfn.TaskInput.from_object({
                "action": "notify_grace",
                "runtime_id": sfn.JsonPath.string_at("$.runtime_id"),
                "runtime_name": sfn.JsonPath.string_at("$.runtime_name"),
                "role_arn": sfn.JsonPath.string_at("$.role_arn")
            }),
            result_path="$.grace_result"
        )

        grace_wait = sfn.Wait(
            self, "ACGracePeriodWait",
            time=sfn.WaitTime.seconds_path("$.grace_period_seconds")
        )

        apply_suspension = tasks.LambdaInvoke(
            self, "ACApplySuspension",
            lambda_function=self.functions["agentcore_iam_utilities"],
            payload=sfn.TaskInput.from_object({
                "action": "apply_restriction",
                "runtime_id": sfn.JsonPath.string_at("$.runtime_id"),
                "role_arn": sfn.JsonPath.string_at("$.role_arn"),
                "account_type": "agentcore_runtime"
            }),
            result_path="$.suspension_result"
        )

        update_status = tasks.DynamoUpdateItem(
            self, "ACUpdateSuspendedStatus",
            table=self.agentcore_budgets_table,
            key={"runtime_id": tasks.DynamoAttributeValue.from_string(
                sfn.JsonPath.string_at("$.runtime_id")
            )},
            update_expression="SET #s = :status",
            expression_attribute_names={"#s": "status"},
            expression_attribute_values={
                ":status": tasks.DynamoAttributeValue.from_string("suspended")
            },
            result_path="$.update_result"
        )

        suspension_success = sfn.Succeed(self, "ACSuspensionSuccess")
        suspension_failed = sfn.Fail(self, "ACSuspensionFailed", cause="Suspension workflow failed")

        suspension_chain = (
            send_grace
            .next(grace_wait)
            .next(apply_suspension)
            .next(update_status)
            .next(suspension_success)
        )

        send_grace.add_catch(suspension_failed)
        apply_suspension.add_catch(suspension_failed)

        self.suspension_state_machine = sfn.StateMachine(
            self, "AgentCoreSuspensionStateMachine",
            state_machine_name=f"bedrock-budgeteer-{self.environment_name}-agentcore-suspension",
            definition_body=sfn.DefinitionBody.from_chainable(suspension_chain),
            role=self.step_functions_role,
            timeout=Duration.minutes(120)
        )

        # Pass state machine ARN to budget monitor
        self.functions["agentcore_budget_monitor"].add_environment(
            "AGENTCORE_SUSPENSION_STATE_MACHINE_ARN",
            self.suspension_state_machine.state_machine_arn
        )

        # --- Restoration Workflow ---
        restore_access = tasks.LambdaInvoke(
            self, "ACRestoreAccess",
            lambda_function=self.functions["agentcore_iam_utilities"],
            payload=sfn.TaskInput.from_object({
                "action": "restore_access",
                "runtime_id": sfn.JsonPath.string_at("$.runtime_id"),
                "role_arn": sfn.JsonPath.string_at("$.role_arn"),
                "account_type": "agentcore_runtime"
            }),
            result_path="$.restore_result"
        )

        validate_restoration = tasks.LambdaInvoke(
            self, "ACValidateRestoration",
            lambda_function=self.functions["agentcore_iam_utilities"],
            payload=sfn.TaskInput.from_object({
                "action": "validate_restrictions",
                "runtime_id": sfn.JsonPath.string_at("$.runtime_id"),
                "role_arn": sfn.JsonPath.string_at("$.role_arn"),
                "account_type": "agentcore_runtime"
            }),
            result_path="$.validation_result"
        )

        reset_budget = tasks.DynamoUpdateItem(
            self, "ACResetBudget",
            table=self.agentcore_budgets_table,
            key={"runtime_id": tasks.DynamoAttributeValue.from_string(
                sfn.JsonPath.string_at("$.runtime_id")
            )},
            update_expression="SET #s = :status, spent_usd = :zero, threshold_state = :normal REMOVE grace_deadline_epoch, policy_snapshot",
            expression_attribute_names={"#s": "status"},
            expression_attribute_values={
                ":status": tasks.DynamoAttributeValue.from_string("active"),
                ":zero": tasks.DynamoAttributeValue.number_from_string("0"),
                ":normal": tasks.DynamoAttributeValue.from_string("normal")
            },
            result_path="$.reset_result"
        )

        restoration_success = sfn.Succeed(self, "ACRestorationSuccess")
        restoration_failed = sfn.Fail(self, "ACRestorationFailed", cause="Restoration workflow failed")

        restoration_chain = (
            restore_access
            .next(validate_restoration)
            .next(reset_budget)
            .next(restoration_success)
        )

        restore_access.add_catch(restoration_failed)

        self.restoration_state_machine = sfn.StateMachine(
            self, "AgentCoreRestorationStateMachine",
            state_machine_name=f"bedrock-budgeteer-{self.environment_name}-agentcore-restoration",
            definition_body=sfn.DefinitionBody.from_chainable(restoration_chain),
            role=self.step_functions_role,
            timeout=Duration.minutes(30)
        )

        # Grant Step Functions permission to invoke Lambda and start executions
        self.suspension_state_machine.grant_start_execution(self.lambda_execution_role)
