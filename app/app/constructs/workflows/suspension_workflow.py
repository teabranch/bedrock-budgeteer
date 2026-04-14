"""
Suspension Workflow
Defines the Step Functions state machine for user suspension workflow
"""
from aws_cdk import (
    aws_stepfunctions as sfn,
    aws_stepfunctions_tasks as sfn_tasks,
)
from .workflow_base import WorkflowBase


class SuspensionWorkflow(WorkflowBase):
    """Defines the suspension workflow state machine"""
    
    def create_suspension_workflow(self) -> sfn.StateMachine:
        """Create Step Functions state machine for user suspension workflow"""
        
        # Define the simplified suspension workflow states
        
        # 1. Send initial grace notification (configurable grace period)
        send_grace_notification = self.create_lambda_invoke_task(
            "SendGraceNotification",
            "grace_period",
            {
                "principal_id.$": "$.principal_id",
                "grace_period_seconds.$": "$.grace_period_seconds",  # Use configurable grace period from input
                "notification_type": "initial"
            },
            "$.grace_notification"
        )
        
        # 2. Grace period wait (dynamic duration based on input)
        grace_period_wait = sfn.Wait(
            self.scope, "GracePeriodWait",
            time=sfn.WaitTime.seconds_path("$.grace_period_seconds")
        )
        
        # 3. Send final warning
        send_final_warning = self.create_lambda_invoke_task(
            "SendFinalWarning",
            "grace_period",
            {
                "principal_id.$": "$.principal_id",
                "notification_type": "final"
            },
            "$.final_warning"
        )
        
        # 4. Apply full suspension (detach AWS managed policy)
        apply_full_suspension = self.create_lambda_invoke_task(
            "ApplyFullSuspension",
            "iam_utilities",
            {
                "action": "apply_restriction",
                "principal_id.$": "$.principal_id",
                "account_type.$": "$.account_type",
                "restriction_level": "full_suspension",
                "suspension_reason.$": "$.suspension_reason"
            },
            "$.suspension_result"
        )
        
        # 5. Update user status to suspended
        update_user_status = self.create_dynamodb_update_task(
            "UpdateUserStatus",
            "user_budgets",
            {
                "principal_id": sfn_tasks.DynamoAttributeValue.from_string(
                    sfn.JsonPath.string_at("$.principal_id")
                )
            },
            "SET #status = :status, suspension_timestamp = :timestamp, suspension_reason = :reason",
            {"#status": "status"},
            {
                ":status": sfn_tasks.DynamoAttributeValue.from_string("suspended"),
                ":timestamp": sfn_tasks.DynamoAttributeValue.from_string(
                    sfn.JsonPath.string_at("$$.State.EnteredTime")
                ),
                ":reason": sfn_tasks.DynamoAttributeValue.from_string(
                    sfn.JsonPath.string_at("$.suspension_reason")
                )
            },
            "$.status_update"
        )
        
        # 6. Success state
        suspension_success = self.create_success_state(
            "SuspensionSuccess",
            "User successfully suspended"
        )
        
        # 7. Failure state (no rollback needed since no policy backup)
        suspension_failure = self.create_failure_state(
            "SuspensionFailed",
            "Suspension workflow failed"
        )
        
        # Build the workflow definition.
        # Each execution handles a single principal_id — batch suspension is implemented
        # by the caller (_trigger_suspension_workflow) starting one execution per key.
        # Input contract: requires principal_id, grace_period_seconds, account_type, suspension_reason.
        definition = send_grace_notification.next(
            grace_period_wait.next(
                send_final_warning.next(
                    apply_full_suspension.next(
                        update_user_status.next(
                            suspension_success
                        )
                    )
                )
            )
        )

        # Add error handling to all workflow steps that can fail
        self.add_error_handling(send_grace_notification, suspension_failure)
        self.add_error_handling(apply_full_suspension, suspension_failure)
        self.add_error_handling(update_user_status, suspension_failure)
        
        # Create the state machine
        return self.create_state_machine(
            "SuspensionWorkflow",
            "suspension",
            definition,
            timeout_minutes=30
        )
