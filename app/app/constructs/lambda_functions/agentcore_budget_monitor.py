"""
AgentCore Budget Monitor Lambda Function
Scans agentcore-budgets table every 5 minutes, checks thresholds,
triggers suspension workflows for per-agent, pool, and global cap violations.
"""


def get_agentcore_budget_monitor_function_code() -> str:
    """Return the AgentCore budget monitor Lambda function code"""
    return '''
import json
import os
import boto3
import logging
from decimal import Decimal
from datetime import datetime, timezone
import time

logger = logging.getLogger()
logger.setLevel(logging.INFO)

dynamodb = boto3.resource('dynamodb')
sfn_client = boto3.client('stepfunctions')
ssm_client = boto3.client('ssm')

def lambda_handler(event, context):
    """Monitor AgentCore runtime budgets and trigger suspension workflows"""
    logger.info("AgentCore budget monitor running")

    try:
        table = dynamodb.Table(os.environ['AGENTCORE_BUDGETS_TABLE'])

        items = _scan_all(table)

        global_pool = None
        budgeted_runtimes = []
        unbudgeted_runtimes = []

        for item in items:
            if item['runtime_id'] == 'GLOBAL_POOL':
                global_pool = item
            elif item.get('status') == 'deleted':
                continue
            elif item.get('budget_limit_usd') is not None:
                budgeted_runtimes.append(item)
            else:
                unbudgeted_runtimes.append(item)

        if not global_pool:
            logger.warning("No GLOBAL_POOL row found, skipping monitoring")
            return {'statusCode': 200, 'message': 'No global pool configured'}

        active_runtimes = budgeted_runtimes + unbudgeted_runtimes
        grace_period_seconds = int(_get_ssm_parameter(
            '/bedrock-budgeteer/global/agentcore/grace_period_seconds', '3600'
        ))
        warning_threshold = float(_get_ssm_parameter(
            '/bedrock-budgeteer/global/agentcore/warning_threshold_percent', '75'
        ))
        critical_threshold = float(_get_ssm_parameter(
            '/bedrock-budgeteer/global/agentcore/critical_threshold_percent', '90'
        ))

        suspensions_triggered = 0

        for runtime in budgeted_runtimes:
            if runtime.get('status') == 'suspended':
                continue
            budget = float(runtime['budget_limit_usd'])
            spent = float(runtime['spent_usd'])
            if budget <= 0:
                continue
            usage_percent = (spent / budget) * 100

            if usage_percent >= 100:
                suspensions_triggered += _handle_budget_exceeded(
                    table, runtime, grace_period_seconds, 'per_agent'
                )
            elif usage_percent >= critical_threshold:
                _update_threshold_state(table, runtime, 'critical')
            elif usage_percent >= warning_threshold:
                _update_threshold_state(table, runtime, 'warning')
            else:
                _update_threshold_state(table, runtime, 'normal')

        pool_spent = sum(float(r.get('spent_usd', 0)) for r in unbudgeted_runtimes)
        pool_budget = float(global_pool['budget_limit_usd'])

        if pool_budget > 0:
            pool_usage_percent = (pool_spent / pool_budget) * 100

            if pool_usage_percent >= 100:
                suspensions_triggered += suspend_unbudgeted_runtimes(
                    table, unbudgeted_runtimes, grace_period_seconds
                )
            elif pool_usage_percent >= critical_threshold:
                _update_threshold_state(table, global_pool, 'critical')
            elif pool_usage_percent >= warning_threshold:
                _update_threshold_state(table, global_pool, 'warning')

        total_spent = float(global_pool.get('spent_usd', 0))
        global_usage_percent = (total_spent / pool_budget) * 100 if pool_budget > 0 else 0

        if global_usage_percent >= 100:
            for runtime in active_runtimes:
                if runtime.get('status') != 'suspended':
                    suspensions_triggered += _handle_budget_exceeded(
                        table, runtime, grace_period_seconds, 'global_cap'
                    )

        MetricsPublisher.publish_budget_metric(
            metric_name='MonitoredAgentRuntimes',
            value=len(active_runtimes),
            unit='Count'
        )
        MetricsPublisher.publish_budget_metric(
            metric_name='AgentPoolUtilizationPercent',
            value=pool_usage_percent if pool_budget > 0 else 0,
            unit='Percent'
        )
        MetricsPublisher.publish_budget_metric(
            metric_name='AgentSuspensionsTriggered',
            value=suspensions_triggered,
            unit='Count'
        )

        return {
            'statusCode': 200,
            'monitored': len(active_runtimes),
            'suspensions_triggered': suspensions_triggered,
            'pool_usage_percent': pool_usage_percent if pool_budget > 0 else 0
        }

    except Exception as e:
        logger.error(f"Error in AgentCore budget monitor: {e}", exc_info=True)
        return {'statusCode': 500, 'error': str(e)}


def _handle_budget_exceeded(table, runtime, grace_period_seconds, reason):
    """Handle a runtime that has exceeded its budget"""
    runtime_id = runtime['runtime_id']
    current_status = runtime.get('status', 'active')

    if current_status == 'suspended':
        return 0

    grace_deadline = runtime.get('grace_deadline_epoch')

    if grace_deadline:
        if time.time() >= float(grace_deadline):
            _trigger_suspension_workflow(runtime, reason)
            return 1
        else:
            logger.info(f"Runtime {runtime_id} in grace period until {grace_deadline}")
            return 0
    else:
        deadline = int(time.time()) + grace_period_seconds
        table.update_item(
            Key={'runtime_id': runtime_id},
            UpdateExpression='SET #s = :status, grace_deadline_epoch = :deadline, grace_period_seconds = :gps',
            ExpressionAttributeNames={'#s': 'status'},
            ExpressionAttributeValues={
                ':status': 'grace_period',
                ':deadline': Decimal(str(deadline)),
                ':gps': grace_period_seconds
            }
        )
        logger.info(f"Started grace period for runtime {runtime_id}, deadline: {deadline}")

        EventPublisher.publish_budget_event(
            event_type='AgentCoreGracePeriodStarted',
            detail={
                'runtime_id': runtime_id,
                'runtime_name': runtime.get('runtime_name', ''),
                'reason': reason,
                'grace_period_seconds': grace_period_seconds
            }
        )
        return 0


def suspend_unbudgeted_runtimes(table, unbudgeted_runtimes, grace_period_seconds):
    """Suspend all unbudgeted runtimes when pool is exhausted"""
    count = 0
    for runtime in unbudgeted_runtimes:
        if runtime.get('status') != 'suspended':
            count += _handle_budget_exceeded(
                table, runtime, grace_period_seconds, 'pool_exhausted'
            )
    return count


def _trigger_suspension_workflow(runtime, reason):
    """Start the AgentCore suspension Step Function"""
    state_machine_arn = os.environ.get('AGENTCORE_SUSPENSION_STATE_MACHINE_ARN', '')
    if not state_machine_arn:
        logger.error("AGENTCORE_SUSPENSION_STATE_MACHINE_ARN not set")
        return

    sfn_input = {
        'runtime_id': runtime['runtime_id'],
        'runtime_name': runtime.get('runtime_name', ''),
        'role_arn': runtime.get('role_arn', ''),
        'account_type': 'agentcore_runtime',
        'reason': reason,
        'grace_period_seconds': int(runtime.get('grace_period_seconds', 3600))
    }

    try:
        sfn_client.start_execution(
            stateMachineArn=state_machine_arn,
            input=json.dumps(sfn_input, default=str)
        )
        logger.info(f"Triggered suspension workflow for runtime {runtime['runtime_id']}")
    except Exception as e:
        logger.error(f"Error triggering suspension workflow: {e}")


def _update_threshold_state(table, item, new_state):
    """Update threshold state if changed"""
    current_state = item.get('threshold_state', 'normal')
    if current_state != new_state:
        table.update_item(
            Key={'runtime_id': item['runtime_id']},
            UpdateExpression='SET threshold_state = :state',
            ExpressionAttributeValues={':state': new_state}
        )
        logger.info(f"Updated {item['runtime_id']} threshold: {current_state} -> {new_state}")

        if new_state in ('warning', 'critical'):
            EventPublisher.publish_budget_event(
                event_type=f'AgentCoreBudget{new_state.title()}',
                detail={
                    'runtime_id': item['runtime_id'],
                    'runtime_name': item.get('runtime_name', ''),
                    'threshold_state': new_state
                }
            )


def _scan_all(table):
    """Scan all items from DynamoDB table with pagination"""
    items = []
    response = table.scan()
    items.extend(response.get('Items', []))
    while 'LastEvaluatedKey' in response:
        response = table.scan(ExclusiveStartKey=response['LastEvaluatedKey'])
        items.extend(response.get('Items', []))
    return items


def _get_ssm_parameter(name, default):
    """Get SSM parameter value with fallback"""
    try:
        response = ssm_client.get_parameter(Name=name)
        return response['Parameter']['Value']
    except Exception:
        return default
'''
