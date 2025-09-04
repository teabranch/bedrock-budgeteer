"""
Workflow Orchestration Construct (Refactored)
Coordinates suspension and restoration workflows using Step Functions
"""
from typing import Dict, Optional
from aws_cdk import (
    Duration,
    RemovalPolicy,
    aws_stepfunctions as sfn,
    aws_lambda as lambda_,
    aws_iam as iam,
    aws_dynamodb as dynamodb,
    aws_sqs as sqs,
    aws_events as events,
    aws_events_targets as targets,
    aws_kms as kms,
    aws_sns as sns,
)
from constructs import Construct

# Import the new modular components
from .workflow_lambda_functions import (
    get_iam_utilities_function_code,
    get_grace_period_function_code,
    get_policy_backup_function_code,
    get_restoration_validation_function_code
)
from .workflows import (
    SuspensionWorkflow,
    RestorationWorkflow
)


class WorkflowOrchestrationConstruct(Construct):
    """Orchestrates suspension and restoration workflows using Step Functions"""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        environment_name: str,
        dynamodb_tables: Dict[str, dynamodb.Table],
        lambda_functions: Dict[str, lambda_.Function],
        step_functions_role: iam.Role,
        lambda_execution_role: iam.Role,
        sns_topics: Optional[Dict[str, sns.Topic]] = None,
        kms_key: Optional[kms.Key] = None,
        **kwargs
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)
        
        self.environment_name = environment_name
        self.dynamodb_tables = dynamodb_tables
        self.lambda_functions = lambda_functions
        self.step_functions_role = step_functions_role
        self.lambda_execution_role = lambda_execution_role
        self.sns_topics = sns_topics or {}
        self.kms_key = kms_key
        
        # Storage for created resources
        self._state_machines: Dict[str, sfn.StateMachine] = {}
        self.workflow_lambda_functions: Dict[str, lambda_.Function] = {}
        self.dlq_queues: Dict[str, sqs.Queue] = {}
        
        # Create workflow-specific Lambda functions
        self._create_workflow_lambda_functions()
        
        # Create suspension workflow
        self._create_suspension_workflow()
        
        # Create restoration workflow  
        self._create_restoration_workflow()
        
        # Set up event routing for workflows
        self._setup_workflow_event_routing()
        
        # Configure Step Functions permissions
        self._configure_step_functions_permissions()
    
    def _create_workflow_lambda_functions(self) -> None:
        """Create Lambda functions specific to workflow operations"""
        
        # Create DLQ for workflow functions
        self._create_workflow_dlqs()
        
        # Create workflow-specific Lambda functions
        self._create_iam_utilities_lambda()
        self._create_grace_period_lambda()

        self._create_policy_backup_lambda()
        self._create_restoration_validation_lambda()
    
    def _create_workflow_dlqs(self) -> None:
        """Create dead letter queues for workflow functions"""
        
        workflow_functions = [
            "iam_utilities",
            "grace_period",

            "policy_backup", 
            "restoration_validation"
        ]
        
        for function_name in workflow_functions:
            dlq_name = f"bedrock-budgeteer-{function_name}-dlq-{self.environment_name}"
            
            self.dlq_queues[function_name] = sqs.Queue(
                self,
                f"{function_name.title().replace('_', '')}DLQ",
                queue_name=dlq_name,
                retention_period=Duration.days(14),
                visibility_timeout=Duration.minutes(5),
                encryption=sqs.QueueEncryption.KMS_MANAGED,
                removal_policy=RemovalPolicy.DESTROY
            )
    
    def _create_iam_utilities_lambda(self) -> None:
        """Create Lambda function for IAM policy management utilities"""
        
        # Use shared Lambda execution role
        iam_utilities_role = self.lambda_execution_role
        
        # Add IAM permissions for policy management
        iam_utilities_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "iam:GetUser",
                    "iam:GetRole",
                    "iam:ListAttachedUserPolicies",
                    "iam:ListAttachedRolePolicies",
                    "iam:ListUserPolicies",
                    "iam:ListRolePolicies",
                    "iam:GetUserPolicy",
                    "iam:GetRolePolicy",
                    "iam:GetPolicy",
                    "iam:GetPolicyVersion",
                    "iam:AttachUserPolicy",
                    "iam:AttachRolePolicy",
                    "iam:DetachUserPolicy", 
                    "iam:DetachRolePolicy",
                    "iam:PutUserPolicy",
                    "iam:PutRolePolicy",
                    "iam:DeleteUserPolicy",
                    "iam:DeleteRolePolicy",
                    "iam:CreatePolicy",
                    "iam:CreatePolicyVersion",
                    "iam:DeletePolicy",
                    "iam:DeletePolicyVersion",
                    "iam:TagUser",
                    "iam:TagRole",
                    "iam:UntagUser",
                    "iam:UntagRole",
                    "iam:ListUserTags"
                ],
                resources=["*"]  # IAM operations often require broad permissions
            )
        )
        
        # Add DynamoDB permissions
        for table in self.dynamodb_tables.values():
            table.grant_read_write_data(iam_utilities_role)
        
        # Add SSM permissions
        iam_utilities_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "ssm:GetParameter",
                    "ssm:GetParameters",
                    "ssm:GetParametersByPath",
                    "ssm:PutParameter"
                ],
                resources=[f"arn:aws:ssm:*:*:parameter/bedrock-budgeteer/*"]
            )
        )
        
        self.workflow_lambda_functions["iam_utilities"] = lambda_.Function(
            self,
            "IAMUtilitiesFunction",
            function_name=f"bedrock-budgeteer-iam-utilities-{self.environment_name}",
            code=lambda_.Code.from_inline(get_iam_utilities_function_code()),
            handler="index.lambda_handler",
            runtime=lambda_.Runtime.PYTHON_3_11,
            timeout=Duration.minutes(5),
            memory_size=512,
            role=iam_utilities_role,
            environment={
                "ENVIRONMENT": self.environment_name,
                "USER_BUDGETS_TABLE": self.dynamodb_tables["user_budgets"].table_name
            },
            dead_letter_queue=self.dlq_queues["iam_utilities"]
        )
    
    def _create_grace_period_lambda(self) -> None:
        """Create Lambda function for grace period notifications"""
        
        # Use shared Lambda execution role
        grace_period_role = self.lambda_execution_role
        
        # Add SNS permissions for notifications
        sns_resources = []
        if self.sns_topics:
            for topic in self.sns_topics.values():
                sns_resources.append(topic.topic_arn)
        
        if sns_resources:
            grace_period_role.add_to_policy(
                iam.PolicyStatement(
                    effect=iam.Effect.ALLOW,
                    actions=[
                        "sns:Publish"
                    ],
                    resources=sns_resources
                )
            )
        else:
            # Fallback to wildcard pattern if no topics provided
            grace_period_role.add_to_policy(
                iam.PolicyStatement(
                    effect=iam.Effect.ALLOW,
                    actions=[
                        "sns:Publish"
                    ],
                    resources=[f"arn:aws:sns:*:*:bedrock-budgeteer-*"]
                )
            )
        
        # Add EventBridge permissions
        grace_period_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "events:PutEvents"
                ],
                resources=[f"arn:aws:events:*:*:event-bus/default"]
            )
        )
        
        # Add STS permissions for account ID lookup
        grace_period_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "sts:GetCallerIdentity"
                ],
                resources=["*"]
            )
        )
        
        # Prepare environment variables with SNS topic ARNs
        environment_vars = {
            "ENVIRONMENT": self.environment_name
        }
        
        # Add SNS topic ARNs if available
        if self.sns_topics:
            if "high_severity" in self.sns_topics:
                environment_vars["HIGH_SEVERITY_TOPIC_ARN"] = self.sns_topics["high_severity"].topic_arn
            if "operational_alerts" in self.sns_topics:
                environment_vars["OPERATIONAL_ALERTS_TOPIC_ARN"] = self.sns_topics["operational_alerts"].topic_arn
            if "budget_alerts" in self.sns_topics:
                environment_vars["BUDGET_ALERTS_TOPIC_ARN"] = self.sns_topics["budget_alerts"].topic_arn
        
        self.workflow_lambda_functions["grace_period"] = lambda_.Function(
            self,
            "GracePeriodFunction",
            function_name=f"bedrock-budgeteer-grace-period-{self.environment_name}",
            code=lambda_.Code.from_inline(get_grace_period_function_code()),
            handler="index.lambda_handler",
            runtime=lambda_.Runtime.PYTHON_3_11,
            timeout=Duration.minutes(2),
            memory_size=256,
            role=grace_period_role,
            environment=environment_vars,
            dead_letter_queue=self.dlq_queues["grace_period"]
        )
    

    
    def _create_policy_backup_lambda(self) -> None:
        """Create Lambda function for policy backup operations"""
        
        # Use shared Lambda execution role
        policy_backup_role = self.lambda_execution_role
        
        self.workflow_lambda_functions["policy_backup"] = lambda_.Function(
            self,
            "PolicyBackupFunction",
            function_name=f"bedrock-budgeteer-policy-backup-{self.environment_name}",
            code=lambda_.Code.from_inline(get_policy_backup_function_code()),
            handler="index.lambda_handler",
            runtime=lambda_.Runtime.PYTHON_3_11,
            timeout=Duration.minutes(1),
            memory_size=256,
            role=policy_backup_role,
            environment={
                "ENVIRONMENT": self.environment_name
            },
            dead_letter_queue=self.dlq_queues["policy_backup"]
        )
    
    def _create_restoration_validation_lambda(self) -> None:
        """Create Lambda function for restoration validation"""
        
        # Use shared Lambda execution role
        restoration_validation_role = self.lambda_execution_role
        
        # Add DynamoDB permissions
        for table in self.dynamodb_tables.values():
            table.grant_read_write_data(restoration_validation_role)
        
        # Add SSM permissions
        restoration_validation_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "ssm:GetParameter",
                    "ssm:GetParameters"
                ],
                resources=[f"arn:aws:ssm:*:*:parameter/bedrock-budgeteer/*"]
            )
        )
        
        self.workflow_lambda_functions["restoration_validation"] = lambda_.Function(
            self,
            "RestorationValidationFunction",
            function_name=f"bedrock-budgeteer-restoration-validation-{self.environment_name}",
            code=lambda_.Code.from_inline(get_restoration_validation_function_code()),
            handler="index.lambda_handler",
            runtime=lambda_.Runtime.PYTHON_3_11,
            timeout=Duration.minutes(3),
            memory_size=256,
            role=restoration_validation_role,
            environment={
                "ENVIRONMENT": self.environment_name,
                "USER_BUDGETS_TABLE": self.dynamodb_tables["user_budgets"].table_name
            },
            dead_letter_queue=self.dlq_queues["restoration_validation"]
        )
    
    def _create_suspension_workflow(self) -> None:
        """Create Step Functions state machine for user suspension workflow"""
        
        # Create the suspension workflow using the modular approach
        suspension_workflow = SuspensionWorkflow(
            scope=self,
            environment_name=self.environment_name,
            dynamodb_tables=self.dynamodb_tables,
            workflow_lambda_functions=self.workflow_lambda_functions,
            step_functions_role=self.step_functions_role
        )
        
        self._state_machines["suspension"] = suspension_workflow.create_suspension_workflow()
    
    def _create_restoration_workflow(self) -> None:
        """Create Step Functions state machine for user restoration workflow"""
        
        # Create the restoration workflow using the modular approach
        restoration_workflow = RestorationWorkflow(
            scope=self,
            environment_name=self.environment_name,
            dynamodb_tables=self.dynamodb_tables,
            workflow_lambda_functions=self.workflow_lambda_functions,
            step_functions_role=self.step_functions_role
        )
        
        self._state_machines["restoration"] = restoration_workflow.create_restoration_workflow()
    
    def _setup_workflow_event_routing(self) -> None:
        """Set up EventBridge rules to trigger workflows"""
        
        # Suspension workflow trigger
        events.Rule(
            self,
            "SuspensionWorkflowTrigger",
            rule_name=f"bedrock-budgeteer-suspension-trigger-{self.environment_name}",
            description="Trigger suspension workflow for budget violations",
            event_pattern=events.EventPattern(
                source=["bedrock-budgeteer"],
                detail_type=["Suspension Workflow Required"]
            ),
            targets=[
                targets.SfnStateMachine(
                    self._state_machines["suspension"],
                    input=events.RuleTargetInput.from_object({
                        "principal_id": events.EventField.from_path("$.detail.principal_id"),
                        "account_type": events.EventField.from_path("$.detail.budget_data.account_type"),
                        "grace_period_seconds": events.EventField.from_path("$.detail.grace_period_seconds"),  # Use configurable grace period from event
                        "restriction_level": "full_suspension",  # Immediate full blocking
                        "trigger_source": "budget_violation"
                    })
                )
            ]
        )
        
        # Automatic restoration workflow trigger (triggered by budget refresh schedule)
        events.Rule(
            self,
            "AutomaticRestorationWorkflowTrigger",
            rule_name=f"bedrock-budgeteer-automatic-restoration-trigger-{self.environment_name}",
            description="Trigger automatic restoration workflow for suspended users when refresh period is reached",
            event_pattern=events.EventPattern(
                source=["bedrock-budgeteer"],
                detail_type=["Automatic User Restoration Required"]
            ),
            targets=[
                targets.SfnStateMachine(
                    self._state_machines["restoration"],
                    input=events.RuleTargetInput.from_object({
                        "principal_id": events.EventField.from_path("$.detail.principal_id"),
                        "restoration_type": "automatic_refresh"
                    })
                )
            ]
        )
    
    def _configure_step_functions_permissions(self) -> None:
        """Configure additional permissions for Step Functions role"""
        
        # Add permissions to invoke Lambda functions
        for function in self.workflow_lambda_functions.values():
            function.grant_invoke(self.step_functions_role)
        
        # Add DynamoDB permissions
        for table in self.dynamodb_tables.values():
            table.grant_read_write_data(self.step_functions_role)
        
        # Add EventBridge permissions
        self.step_functions_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "events:PutEvents"
                ],
                resources=[f"arn:aws:events:*:*:event-bus/default"]
            )
        )
        
        # Add SQS permissions for DLQ access
        for dlq in self.dlq_queues.values():
            dlq.grant_send_messages(self.step_functions_role)
    
    # Public properties to expose resources
    @property
    def suspension_state_machine(self) -> sfn.StateMachine:
        """Expose suspension state machine"""
        return self._state_machines["suspension"]
    
    @property
    def restoration_state_machine(self) -> sfn.StateMachine:
        """Expose restoration state machine"""
        return self._state_machines["restoration"]
    
    @property
    def workflow_functions(self) -> Dict[str, lambda_.Function]:
        """Expose workflow Lambda functions"""
        return self.workflow_lambda_functions
    
    @property
    def workflow_dlqs(self) -> Dict[str, sqs.Queue]:
        """Expose workflow DLQ queues"""
        return self.dlq_queues
    
    @property
    def state_machines(self) -> Dict[str, sfn.StateMachine]:
        """Expose state machines"""
        return self._state_machines
