"""
Workflow Base Class
Provides common utilities and base functionality for workflow state machines
"""
from typing import Dict, Any
from aws_cdk import (
    Duration,
    RemovalPolicy,
    aws_stepfunctions as sfn,
    aws_stepfunctions_tasks as sfn_tasks,
    aws_lambda as lambda_,
    aws_iam as iam,
    aws_dynamodb as dynamodb,
    aws_logs as logs,
)
from constructs import Construct


class WorkflowBase:
    """Base class for workflow state machine definitions"""
    
    def __init__(
        self,
        scope: Construct,
        environment_name: str,
        dynamodb_tables: Dict[str, dynamodb.Table],
        workflow_lambda_functions: Dict[str, lambda_.Function],
        step_functions_role: iam.Role
    ):
        self.scope = scope
        self.environment_name = environment_name
        self.dynamodb_tables = dynamodb_tables
        self.workflow_lambda_functions = workflow_lambda_functions
        self.step_functions_role = step_functions_role
    
    def create_lambda_invoke_task(
        self,
        task_id: str,
        function_name: str,
        payload: Dict[str, Any],
        result_path: str = None
    ) -> sfn_tasks.LambdaInvoke:
        """Create a Lambda invoke task with standardized configuration"""
        task = sfn_tasks.LambdaInvoke(
            self.scope,
            task_id,
            lambda_function=self.workflow_lambda_functions[function_name],
            payload=sfn.TaskInput.from_object(payload),
            result_path=result_path
        )
        return task
    
    def create_dynamodb_update_task(
        self,
        task_id: str,
        table_name: str,
        key: Dict[str, Any],
        update_expression: str,
        expression_attribute_names: Dict[str, str] = None,
        expression_attribute_values: Dict[str, Any] = None,
        result_path: str = None
    ) -> sfn_tasks.DynamoUpdateItem:
        """Create a DynamoDB update task with standardized configuration"""
        task = sfn_tasks.DynamoUpdateItem(
            self.scope,
            task_id,
            table=self.dynamodb_tables[table_name],
            key=key,
            update_expression=update_expression,
            expression_attribute_names=expression_attribute_names or {},
            expression_attribute_values=expression_attribute_values or {},
            result_path=result_path
        )
        return task
    
    def create_log_group(
        self,
        log_group_id: str,
        workflow_name: str
    ) -> logs.LogGroup:
        """Create a log group for the workflow"""
        return logs.LogGroup(
            self.scope,
            log_group_id,
            log_group_name=f"/aws/stepfunctions/bedrock-budgeteer-{workflow_name}-{self.environment_name}",
            retention=logs.RetentionDays.ONE_MONTH,
            removal_policy=RemovalPolicy.DESTROY
        )
    
    def create_state_machine(
        self,
        state_machine_id: str,
        workflow_name: str,
        definition: sfn.IChainable,
        timeout_minutes: int = 30
    ) -> sfn.StateMachine:
        """Create a state machine with standardized configuration"""
        log_group = self.create_log_group(f"{state_machine_id}Logs", workflow_name)
        
        return sfn.StateMachine(
            self.scope,
            state_machine_id,
            state_machine_name=f"bedrock-budgeteer-{workflow_name}-{self.environment_name}",
            definition_body=sfn.DefinitionBody.from_chainable(definition),
            role=self.step_functions_role,
            timeout=Duration.minutes(timeout_minutes),
            logs=sfn.LogOptions(
                destination=log_group,
                level=sfn.LogLevel.ALL,
                include_execution_data=True
            )
        )
    
    def create_choice_condition(
        self,
        condition_type: str,
        path: str,
        value: Any
    ) -> sfn.Condition:
        """Create common choice conditions"""
        if condition_type == "boolean_equals":
            return sfn.Condition.boolean_equals(path, value)
        elif condition_type == "string_equals":
            return sfn.Condition.string_equals(path, value)
        elif condition_type == "number_equals":
            return sfn.Condition.number_equals(path, value)
        elif condition_type == "number_greater_than":
            return sfn.Condition.number_greater_than(path, value)
        elif condition_type == "number_less_than":
            return sfn.Condition.number_less_than(path, value)
        else:
            raise ValueError(f"Unsupported condition type: {condition_type}")
    
    def create_failure_state(
        self,
        state_id: str,
        comment: str,
        cause: str = None,
        error: str = None
    ) -> sfn.Fail:
        """Create a standardized failure state"""
        return sfn.Fail(
            self.scope,
            state_id,
            comment=comment,
            cause=cause,
            error=error
        )
    
    def create_success_state(
        self,
        state_id: str,
        comment: str
    ) -> sfn.Succeed:
        """Create a standardized success state"""
        return sfn.Succeed(
            self.scope,
            state_id,
            comment=comment
        )
    
    def create_wait_state(
        self,
        state_id: str,
        wait_time: Duration = None,
        wait_seconds_path: str = None
    ) -> sfn.Wait:
        """Create a wait state with either fixed duration or dynamic path"""
        if wait_time:
            return sfn.Wait(
                self.scope,
                state_id,
                time=sfn.WaitTime.duration(wait_time)
            )
        elif wait_seconds_path:
            return sfn.Wait(
                self.scope,
                state_id,
                time=sfn.WaitTime.seconds_path(wait_seconds_path)
            )
        else:
            raise ValueError("Either wait_time or wait_seconds_path must be provided")
    
    def add_error_handling(
        self,
        task: sfn.TaskStateBase,
        catch_state: sfn.State,
        errors: list = None
    ) -> sfn.TaskStateBase:
        """Add error handling to a task"""
        task.add_catch(
            catch_state,
            errors=errors or ["States.ALL"]
        )
        return task
