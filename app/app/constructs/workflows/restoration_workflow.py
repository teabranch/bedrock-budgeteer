"""
Restoration Workflow
Defines the Step Functions state machine for user restoration workflow
"""
from aws_cdk import (
    aws_stepfunctions as sfn,
    aws_stepfunctions_tasks as sfn_tasks,
)
from .workflow_base import WorkflowBase


class RestorationWorkflow(WorkflowBase):
    """Defines the restoration workflow state machine"""
    
    def create_restoration_workflow(self) -> sfn.StateMachine:
        """Create Step Functions state machine for automatic user restoration workflow"""
        
        # Define the automatic restoration workflow states
        
        # 1. Validate automatic restoration (check refresh period)
        validate_automatic_restoration = self.create_lambda_invoke_task(
            "ValidateAutomaticRestoration",
            "restoration_validation",
            {
                "principal_id.$": "$.principal_id",
                "validation_type": "automatic_refresh"
            },
            "$.validation_result"
        )
        
        # 2. Validation choice
        validation_choice = sfn.Choice(self.scope, "ValidationChoice")
        
        # 3. Restore Bedrock access
        restore_access = self.create_lambda_invoke_task(
            "RestoreAccess",
            "iam_utilities",
            {
                "action": "restore_access",
                "principal_id.$": "$.principal_id",
                "account_type": "bedrock_api_key"
            },
            "$.restore_result"
        )
        
        # 4. Validate access restoration
        validate_access_restoration = self.create_lambda_invoke_task(
            "ValidateAccessRestoration",
            "iam_utilities",
            {
                "action": "validate_restrictions",
                "principal_id.$": "$.principal_id",
                "account_type": "bedrock_api_key",
                "restriction_level": "full_suspension"
            },
            "$.restoration_validation"
        )
        
        # 5. Reset budget status (reset spent amount and update refresh date)
        reset_budget_status = self.create_dynamodb_update_task(
            "ResetBudgetStatus",
            "user_budgets",
            {
                "principal_id": sfn_tasks.DynamoAttributeValue.from_string(
                    sfn.JsonPath.string_at("$.principal_id")
                )
            },
            "SET #status = :status, spent_usd = :zero, threshold_state = :normal, restoration_timestamp = :timestamp, last_restoration_timestamp = :timestamp, budget_period_start = :period_start, budget_refresh_date = :next_refresh REMOVE restoration_status, restoration_start_epoch",
            {"#status": "status"},
            {
                ":status": sfn_tasks.DynamoAttributeValue.from_string("active"),
                ":zero": sfn_tasks.DynamoAttributeValue.from_number(0),
                ":normal": sfn_tasks.DynamoAttributeValue.from_string("normal"),
                ":timestamp": sfn_tasks.DynamoAttributeValue.from_string(
                    sfn.JsonPath.string_at("$$.State.EnteredTime")
                ),
                ":period_start": sfn_tasks.DynamoAttributeValue.from_string(
                    sfn.JsonPath.string_at("$$.State.EnteredTime")
                ),
                ":next_refresh": sfn_tasks.DynamoAttributeValue.from_string(
                    sfn.JsonPath.string_at("$.validation_result.Payload.next_refresh_date")
                )
            },
            "$.budget_reset"
        )
        
        # 6. Log restoration audit event
        log_restoration_audit = sfn_tasks.EventBridgePutEvents(
            self.scope, "LogRestorationAudit",
            entries=[
                sfn_tasks.EventBridgePutEventsEntry(
                    source="bedrock-budgeteer",
                    detail_type="User Access Automatically Restored",
                    detail=sfn.TaskInput.from_object({
                        "principal_id.$": "$.principal_id",
                        "restored_by": "automatic-budget-refresh",
                        "restoration_type": "budget_refresh_period",
                        "timestamp.$": "$$.State.EnteredTime"
                    })
                )
            ],
            result_path="$.audit_logged"
        )
        
        # 7. Send restoration notification
        send_restoration_notification = self.create_lambda_invoke_task(
            "SendRestorationNotification",
            "grace_period",
            {
                "principal_id.$": "$.principal_id",
                "notification_type": "automatic_restoration_complete"
            },
            "$.notification_sent"
        )
        
        # 8. Restoration success
        restoration_success = self.create_success_state(
            "RestorationSuccess",
            "User access automatically restored"
        )
        
        # 9. Validation failed
        validation_failed = self.create_failure_state(
            "ValidationFailed",
            "Automatic restoration validation failed"
        )
        
        # 10. Restoration failure
        restoration_failure = self.create_failure_state(
            "RestorationFailed",
            "Automatic restoration workflow failed"
        )
        
        # Build the simplified automatic workflow definition
        definition = validate_automatic_restoration.next(
            validation_choice
            .when(
                self.create_choice_condition(
                    "boolean_equals",
                    "$.validation_result.Payload.validation_result.is_valid",
                    False
                ),
                validation_failed
            )
            .otherwise(
                restore_access.next(
                    validate_access_restoration.next(
                        reset_budget_status.next(
                            log_restoration_audit.next(
                                send_restoration_notification.next(
                                    restoration_success
                                )
                            )
                        )
                    )
                )
            )
        )
        
        # Add error handling
        self.add_error_handling(restore_access, restoration_failure)
        self.add_error_handling(reset_budget_status, restoration_failure)
        
        # Create the state machine
        return self.create_state_machine(
            "AutomaticRestorationWorkflow",
            "restoration",
            definition,
            timeout_minutes=10
        )
