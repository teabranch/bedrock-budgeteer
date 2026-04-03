"""
AgentCore Setup Lambda Function
Registers new AgentCore runtimes, updates metadata, and handles deletions.
Triggered by EventBridge rule on bedrock-agentcore.amazonaws.com lifecycle events.
"""


def get_agentcore_setup_function_code() -> str:
    """Return the AgentCore setup Lambda function code"""
    return '''
import json
import os
import boto3
import logging
from decimal import Decimal
from datetime import datetime, timezone, timedelta

logger = logging.getLogger()
logger.setLevel(logging.INFO)

dynamodb = boto3.resource('dynamodb')
ssm_client = boto3.client('ssm')

def lambda_handler(event, context):
    """Process AgentCore lifecycle events from EventBridge"""
    logger.info(f"AgentCore setup event received: {json.dumps(event, default=str)}")

    try:
        detail = event.get('detail', {})
        event_name = detail.get('eventName', '')

        if event_name == 'CreateAgentRuntime':
            return handle_create_runtime(detail)
        elif event_name == 'DeleteAgentRuntime':
            return handle_delete_runtime(detail)
        elif event_name == 'UpdateAgentRuntime':
            return handle_update_runtime(detail)
        else:
            logger.info(f"Ignoring unhandled event: {event_name}")
            return {'statusCode': 200, 'message': f'Ignored event: {event_name}'}

    except Exception as e:
        logger.error(f"Error processing AgentCore setup event: {e}", exc_info=True)
        return {'statusCode': 500, 'error': str(e)}


def handle_create_runtime(detail):
    """Register a new AgentCore runtime"""
    request_params = detail.get('requestParameters', {})
    response_elements = detail.get('responseElements', {})
    user_identity = detail.get('userIdentity', {})

    runtime_id = response_elements.get('agentRuntimeId', '')
    runtime_name = request_params.get('agentRuntimeName', '')
    role_arn = request_params.get('roleArn', '')
    runtime_arn = response_elements.get('agentRuntimeArn', '')

    if not runtime_id or not role_arn:
        logger.error("Missing agentRuntimeId or roleArn in event")
        return {'statusCode': 400, 'error': 'Missing required fields'}

    creator_arn = user_identity.get('arn', '')

    table = dynamodb.Table(os.environ['AGENTCORE_BUDGETS_TABLE'])
    now = datetime.now(timezone.utc)

    default_budget = _get_ssm_parameter(
        '/bedrock-budgeteer/global/agentcore/default_per_agent_budget_usd',
        None
    )
    refresh_days = int(_get_ssm_parameter(
        '/bedrock-budgeteer/global/agentcore/refresh_period_days',
        '30'
    ))

    try:
        budget_item = {
            'runtime_id': runtime_id,
            'runtime_name': runtime_name,
            'role_arn': role_arn,
            'runtime_arn': runtime_arn,
            'budget_limit_usd': Decimal(str(default_budget)) if default_budget else None,
            'spent_usd': Decimal('0'),
            'status': 'active',
            'threshold_state': 'normal',
            'refresh_period_days': refresh_days,
            'budget_refresh_date': (now + timedelta(days=refresh_days)).isoformat(),
            'creator_arn': creator_arn,
            'created_at': now.isoformat()
        }

        budget_item = {k: v for k, v in budget_item.items() if v is not None}

        table.put_item(
            Item=budget_item,
            ConditionExpression='attribute_not_exists(runtime_id)'
        )
        logger.info(f"Registered new AgentCore runtime: {runtime_id} ({runtime_name})")

    except dynamodb.meta.client.exceptions.ConditionalCheckFailedException:
        logger.info(f"Runtime {runtime_id} already registered, skipping")
        return {'statusCode': 200, 'message': 'Runtime already registered'}

    _ensure_global_pool(table)
    _check_duplicate_role_arn(table, role_arn, runtime_id)

    EventPublisher.publish_budget_event(
        event_type='AgentCoreRuntimeRegistered',
        detail={
            'runtime_id': runtime_id,
            'runtime_name': runtime_name,
            'role_arn': role_arn,
            'creator_arn': creator_arn
        }
    )

    MetricsPublisher.publish_budget_metric(
        metric_name='AgentCoreRuntimeRegistered',
        value=1,
        unit='Count'
    )

    return {'statusCode': 200, 'runtime_id': runtime_id}


def handle_delete_runtime(detail):
    """Mark a runtime as deleted (preserve for audit)"""
    response_elements = detail.get('responseElements', {})
    request_params = detail.get('requestParameters', {})

    runtime_id = response_elements.get('agentRuntimeId', '') or request_params.get('agentRuntimeId', '')

    if not runtime_id:
        logger.error("Missing agentRuntimeId in delete event")
        return {'statusCode': 400, 'error': 'Missing agentRuntimeId'}

    table = dynamodb.Table(os.environ['AGENTCORE_BUDGETS_TABLE'])

    try:
        table.update_item(
            Key={'runtime_id': runtime_id},
            UpdateExpression='SET #s = :status, deleted_at = :ts',
            ExpressionAttributeNames={'#s': 'status'},
            ExpressionAttributeValues={
                ':status': 'deleted',
                ':ts': datetime.now(timezone.utc).isoformat()
            },
            ConditionExpression='attribute_exists(runtime_id)'
        )
        logger.info(f"Marked runtime {runtime_id} as deleted")

        table.update_item(
            Key={'runtime_id': runtime_id},
            UpdateExpression='REMOVE policy_snapshot'
        )

    except dynamodb.meta.client.exceptions.ConditionalCheckFailedException:
        logger.warning(f"Runtime {runtime_id} not found for deletion")

    EventPublisher.publish_budget_event(
        event_type='AgentCoreRuntimeDeleted',
        detail={'runtime_id': runtime_id}
    )

    return {'statusCode': 200, 'runtime_id': runtime_id}


def handle_update_runtime(detail):
    """Update runtime metadata (role_arn, name) if changed"""
    request_params = detail.get('requestParameters', {})
    response_elements = detail.get('responseElements', {})

    runtime_id = response_elements.get('agentRuntimeId', '') or request_params.get('agentRuntimeId', '')
    new_role_arn = request_params.get('roleArn')
    new_name = request_params.get('agentRuntimeName')

    if not runtime_id:
        logger.error("Missing agentRuntimeId in update event")
        return {'statusCode': 400, 'error': 'Missing agentRuntimeId'}

    table = dynamodb.Table(os.environ['AGENTCORE_BUDGETS_TABLE'])

    update_parts = []
    expr_values = {}

    if new_role_arn:
        update_parts.append('role_arn = :role_arn')
        expr_values[':role_arn'] = new_role_arn
    if new_name:
        update_parts.append('runtime_name = :name')
        expr_values[':name'] = new_name

    if update_parts:
        update_parts.append('updated_at = :ts')
        expr_values[':ts'] = datetime.now(timezone.utc).isoformat()

        table.update_item(
            Key={'runtime_id': runtime_id},
            UpdateExpression='SET ' + ', '.join(update_parts),
            ExpressionAttributeValues=expr_values
        )
        logger.info(f"Updated runtime {runtime_id} metadata")

    return {'statusCode': 200, 'runtime_id': runtime_id}


def _ensure_global_pool(table):
    """Create the GLOBAL_POOL row if it doesn't exist"""
    now = datetime.now(timezone.utc)
    global_budget = Decimal(_get_ssm_parameter(
        '/bedrock-budgeteer/global/agentcore/global_budget_limit_usd',
        '500'
    ))
    refresh_days = int(_get_ssm_parameter(
        '/bedrock-budgeteer/global/agentcore/refresh_period_days',
        '30'
    ))

    try:
        table.put_item(
            Item={
                'runtime_id': 'GLOBAL_POOL',
                'runtime_name': 'Global AgentCore Budget',
                'budget_limit_usd': global_budget,
                'spent_usd': Decimal('0'),
                'status': 'active',
                'threshold_state': 'normal',
                'refresh_period_days': refresh_days,
                'budget_refresh_date': (now + timedelta(days=refresh_days)).isoformat(),
                'created_at': now.isoformat()
            },
            ConditionExpression='attribute_not_exists(runtime_id)'
        )
        logger.info("Created GLOBAL_POOL row")
    except dynamodb.meta.client.exceptions.ConditionalCheckFailedException:
        pass


def _check_duplicate_role_arn(table, role_arn, current_runtime_id):
    """Warn if another active runtime uses the same execution role"""
    try:
        response = table.query(
            IndexName='role_arn-index',
            KeyConditionExpression='role_arn = :arn',
            ExpressionAttributeValues={':arn': role_arn}
        )
        for item in response.get('Items', []):
            if item['runtime_id'] != current_runtime_id and item.get('status') != 'deleted':
                logger.warning(
                    f"Role ARN {role_arn} is shared between runtimes: "
                    f"{current_runtime_id} and {item['runtime_id']}. "
                    f"Suspending one will affect both."
                )
    except Exception as e:
        logger.warning(f"Could not check for duplicate role ARN: {e}")


def _get_ssm_parameter(name, default):
    """Get SSM parameter value with fallback"""
    try:
        response = ssm_client.get_parameter(Name=name)
        return response['Parameter']['Value']
    except Exception:
        return default
'''
