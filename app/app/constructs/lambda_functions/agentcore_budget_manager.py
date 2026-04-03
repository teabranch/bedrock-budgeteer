"""
AgentCore Budget Manager Lambda Function
CRUD API for managing AgentCore runtime budgets, exposed via Lambda Function URL.
"""


def get_agentcore_budget_manager_function_code() -> str:
    """Return the AgentCore budget manager Lambda function code"""
    return '''
import json
import os
import boto3
import logging
from decimal import Decimal

logger = logging.getLogger()
logger.setLevel(logging.INFO)

dynamodb = boto3.resource('dynamodb')


def lambda_handler(event, context):
    """Handle budget management requests from Lambda Function URL.

    Response envelope format:
        {"success": true/false, "data": {...}, "error": null/string}
    """
    logger.info(f"Budget manager request: {json.dumps(event, default=str)}")

    try:
        body = event.get('body', '{}')
        if isinstance(body, str):
            body = json.loads(body)

        action = body.get('action', '')

        if action == 'set_agent_budget':
            result = handle_set_agent_budget(body)
        elif action == 'remove_agent_budget':
            result = handle_remove_agent_budget(body)
        elif action == 'set_global_budget':
            result = handle_set_global_budget(body)
        elif action == 'get_budget_status':
            result = handle_get_budget_status(body)
        else:
            result = {'success': False, 'data': None, 'error': f'Unknown action: {action}'}

        return {
            'statusCode': 200,
            'headers': {'Content-Type': 'application/json'},
            'body': json.dumps(result, default=str)
        }

    except Exception as e:
        logger.error(f"Error in budget manager: {e}", exc_info=True)
        return {
            'statusCode': 500,
            'headers': {'Content-Type': 'application/json'},
            'body': json.dumps({'success': False, 'data': None, 'error': str(e)})
        }


def handle_set_agent_budget(body):
    """Assign or update a per-agent budget"""
    runtime_id = body.get('runtime_id')
    budget_limit = body.get('budget_limit_usd')

    if not runtime_id or budget_limit is None:
        return {'success': False, 'data': None, 'error': 'runtime_id and budget_limit_usd required'}

    budget_limit = Decimal(str(budget_limit))
    table = dynamodb.Table(os.environ['AGENTCORE_BUDGETS_TABLE'])

    response = table.get_item(Key={'runtime_id': runtime_id})
    if 'Item' not in response:
        return {'success': False, 'data': None, 'error': f'Runtime {runtime_id} not found'}

    runtime = response['Item']
    if runtime.get('status') == 'suspended':
        return {'success': False, 'data': None, 'error': 'Cannot modify budget of suspended runtime'}

    pool_response = table.get_item(Key={'runtime_id': 'GLOBAL_POOL'})
    if 'Item' in pool_response:
        global_limit = pool_response['Item'].get('budget_limit_usd', Decimal('0'))
        if budget_limit > global_limit:
            return {
                'success': False, 'data': None,
                'error': f'Budget {budget_limit} exceeds global pool limit {global_limit}'
            }

    table.update_item(
        Key={'runtime_id': runtime_id},
        UpdateExpression='SET budget_limit_usd = :limit',
        ExpressionAttributeValues={':limit': budget_limit}
    )

    EventPublisher.publish_budget_event(
        event_type='AgentCoreBudgetUpdated',
        detail={'runtime_id': runtime_id, 'budget_limit_usd': str(budget_limit)}
    )

    return {'success': True, 'data': {'runtime_id': runtime_id, 'budget_limit_usd': str(budget_limit)}, 'error': None}


def handle_remove_agent_budget(body):
    """Remove per-agent budget, returning agent to pool"""
    runtime_id = body.get('runtime_id')
    if not runtime_id:
        return {'success': False, 'data': None, 'error': 'runtime_id required'}

    table = dynamodb.Table(os.environ['AGENTCORE_BUDGETS_TABLE'])

    response = table.get_item(Key={'runtime_id': runtime_id})
    if 'Item' not in response:
        return {'success': False, 'data': None, 'error': f'Runtime {runtime_id} not found'}

    table.update_item(
        Key={'runtime_id': runtime_id},
        UpdateExpression='REMOVE budget_limit_usd'
    )

    EventPublisher.publish_budget_event(
        event_type='AgentCoreBudgetRemoved',
        detail={'runtime_id': runtime_id}
    )

    return {'success': True, 'data': {'runtime_id': runtime_id, 'budget_limit_usd': None}, 'error': None}


def handle_set_global_budget(body):
    """Update the global pool budget limit"""
    budget_limit = body.get('budget_limit_usd')
    if budget_limit is None:
        return {'success': False, 'data': None, 'error': 'budget_limit_usd required'}

    budget_limit = Decimal(str(budget_limit))
    table = dynamodb.Table(os.environ['AGENTCORE_BUDGETS_TABLE'])

    items = _scan_all(table)
    total_allocated = Decimal('0')
    for item in items:
        if item['runtime_id'] != 'GLOBAL_POOL' and item.get('budget_limit_usd') is not None:
            total_allocated += item['budget_limit_usd']

    if budget_limit < total_allocated:
        return {
            'success': False, 'data': None,
            'error': f'New limit {budget_limit} is below total allocated per-agent budgets {total_allocated}'
        }

    table.update_item(
        Key={'runtime_id': 'GLOBAL_POOL'},
        UpdateExpression='SET budget_limit_usd = :limit',
        ExpressionAttributeValues={':limit': budget_limit}
    )

    EventPublisher.publish_budget_event(
        event_type='AgentCoreGlobalBudgetUpdated',
        detail={'budget_limit_usd': str(budget_limit)}
    )

    return {'success': True, 'data': {'budget_limit_usd': str(budget_limit)}, 'error': None}


def handle_get_budget_status(body):
    """Get budget status for a runtime or global overview"""
    runtime_id = body.get('runtime_id')
    table = dynamodb.Table(os.environ['AGENTCORE_BUDGETS_TABLE'])

    if runtime_id:
        response = table.get_item(Key={'runtime_id': runtime_id})
        if 'Item' not in response:
            return {'success': False, 'data': None, 'error': f'Runtime {runtime_id} not found'}
        return {'success': True, 'data': _serialize_item(response['Item']), 'error': None}

    items = _scan_all(table)
    global_pool = None
    runtimes = []
    for item in items:
        if item['runtime_id'] == 'GLOBAL_POOL':
            global_pool = _serialize_item(item)
        elif item.get('status') != 'deleted':
            runtimes.append(_serialize_item(item))

    return {
        'success': True,
        'data': {'global_pool': global_pool, 'runtimes': runtimes, 'total_runtimes': len(runtimes)},
        'error': None
    }


def _serialize_item(item):
    """Convert DynamoDB Decimal types to strings for JSON serialization"""
    result = {}
    for k, v in item.items():
        if isinstance(v, Decimal):
            result[k] = str(v)
        else:
            result[k] = v
    return result


def _scan_all(table):
    """Scan all items from DynamoDB table"""
    items = []
    response = table.scan()
    items.extend(response.get('Items', []))
    while 'LastEvaluatedKey' in response:
        response = table.scan(ExclusiveStartKey=response['LastEvaluatedKey'])
        items.extend(response.get('Items', []))
    return items
'''
