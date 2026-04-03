"""
AgentCore Helpers - shared utility concatenated into Lambda inline code.
Provides role ARN lookup, budget attribution, and global pool update functions.
"""


def get_agentcore_helpers() -> str:
    """Return the AgentCore helpers code to be concatenated into Lambda functions"""
    return '''
import os
import boto3
import logging
from decimal import Decimal
from datetime import datetime, timezone

# AgentCore helpers - initialized lazily
_agentcore_table = None
_agentcore_table_name = None

logger = logging.getLogger()

def _get_agentcore_table():
    """Lazy-initialize the AgentCore budgets DynamoDB table"""
    global _agentcore_table, _agentcore_table_name
    if _agentcore_table is None:
        _agentcore_table_name = os.environ.get('AGENTCORE_BUDGETS_TABLE', '')
        if _agentcore_table_name:
            dynamodb_resource = boto3.resource('dynamodb')
            _agentcore_table = dynamodb_resource.Table(_agentcore_table_name)
    return _agentcore_table


def extract_role_arn_from_event(event_detail):
    """Extract the caller role ARN from a CloudTrail event detail.

    Returns the role ARN if the caller is an AssumedRole, None otherwise.
    This is used to determine if a Bedrock API call was made by an AgentCore runtime.
    """
    user_identity = event_detail.get('userIdentity', {})

    if user_identity.get('type') != 'AssumedRole':
        return None

    session_context = user_identity.get('sessionContext', {})
    session_issuer = session_context.get('sessionIssuer', {})
    role_arn = session_issuer.get('arn')

    return role_arn


def lookup_runtime_by_role_arn(role_arn):
    """Look up an AgentCore runtime by its execution role ARN using the GSI.

    Returns the runtime item dict if found, None otherwise.
    """
    table = _get_agentcore_table()
    if table is None:
        return None

    try:
        response = table.query(
            IndexName='role_arn-index',
            KeyConditionExpression='role_arn = :arn',
            ExpressionAttributeValues={':arn': role_arn},
            Limit=1
        )
        items = response.get('Items', [])
        if items:
            runtime = items[0]
            # Skip deleted runtimes
            if runtime.get('status') == 'deleted':
                return None
            return runtime
        return None
    except Exception as e:
        logger.error(f"Error looking up runtime by role ARN {role_arn}: {e}")
        return None


def update_runtime_budget(runtime_id, cost_usd):
    """Increment spent_usd on a runtime's budget row.

    Args:
        runtime_id: The AgentCore runtime ID
        cost_usd: Cost in USD to add (as float or Decimal)
    """
    table = _get_agentcore_table()
    if table is None:
        return

    try:
        table.update_item(
            Key={'runtime_id': runtime_id},
            UpdateExpression='SET spent_usd = spent_usd + :cost, last_usage_timestamp = :ts',
            ExpressionAttributeValues={
                ':cost': Decimal(str(cost_usd)),
                ':ts': datetime.now(timezone.utc).isoformat()
            }
        )
    except Exception as e:
        logger.error(f"Error updating runtime budget for {runtime_id}: {e}")
        raise


def update_global_pool(cost_usd):
    """Increment spent_usd on the GLOBAL_POOL row.

    Args:
        cost_usd: Cost in USD to add (as float or Decimal)
    """
    table = _get_agentcore_table()
    if table is None:
        return

    try:
        table.update_item(
            Key={'runtime_id': 'GLOBAL_POOL'},
            UpdateExpression='SET spent_usd = spent_usd + :cost, last_usage_timestamp = :ts',
            ExpressionAttributeValues={
                ':cost': Decimal(str(cost_usd)),
                ':ts': datetime.now(timezone.utc).isoformat()
            }
        )
    except Exception as e:
        logger.error(f"Error updating global pool: {e}")
        raise
'''
