"""
Cost Reconciliation Lambda Function Code
Daily Lambda that compares Cost Explorer totals with internal usage_tracking data
to detect drift between AWS billing and the system's own cost calculations.
"""


def get_cost_reconciliation_function_code() -> str:
    """Return the inline Lambda function code for cost reconciliation"""
    return '''
import os
import json
import logging
from datetime import datetime, timedelta
from decimal import Decimal

import boto3
from boto3.dynamodb.conditions import Attr

logger = logging.getLogger()
logger.setLevel(logging.INFO)

ce_client = boto3.client('ce')
cloudwatch_client = boto3.client('cloudwatch')
sns_client = boto3.client('sns')
dynamodb = boto3.resource('dynamodb')

METRIC_NAMESPACE = 'BedrockBudgeteer/CostAllocation'
ENVIRONMENT = os.environ.get('ENVIRONMENT', 'production')
USAGE_TRACKING_TABLE = os.environ.get('USAGE_TRACKING_TABLE', '')
OPERATIONAL_ALERTS_SNS_TOPIC_ARN = os.environ.get('OPERATIONAL_ALERTS_SNS_TOPIC_ARN', '')
DRIFT_THRESHOLD_PERCENT = 10.0


def lambda_handler(event, context):
    """Compare Cost Explorer total with internal tracking and publish drift metric"""
    logger.info("Starting cost reconciliation")

    # Query yesterday's costs (Cost Explorer has ~24h delay)
    yesterday = (datetime.utcnow() - timedelta(days=1)).strftime('%Y-%m-%d')
    today = datetime.utcnow().strftime('%Y-%m-%d')

    try:
        ce_total = _get_cost_explorer_total(yesterday, today)
        internal_total = _get_internal_tracking_total(yesterday, today)

        drift_percent = _calculate_drift(ce_total, internal_total)

        _publish_drift_metric(drift_percent)

        if abs(drift_percent) > DRIFT_THRESHOLD_PERCENT:
            _send_drift_alert(ce_total, internal_total, drift_percent)

        logger.info(
            f"Reconciliation complete: CE=${ce_total:.4f}, "
            f"Internal=${internal_total:.4f}, Drift={drift_percent:.2f}%"
        )

        return {
            'statusCode': 200,
            'body': json.dumps({
                'cost_explorer_total': float(ce_total),
                'internal_total': float(internal_total),
                'drift_percent': float(drift_percent),
                'alert_sent': abs(drift_percent) > DRIFT_THRESHOLD_PERCENT
            })
        }

    except Exception as e:
        logger.error(f"Cost reconciliation failed: {str(e)}")
        raise


def _get_cost_explorer_total(start_date, end_date):
    """Get total Bedrock cost from Cost Explorer for the given date range"""
    try:
        response = ce_client.get_cost_and_usage(
            TimePeriod={'Start': start_date, 'End': end_date},
            Granularity='DAILY',
            Filter={
                'Dimensions': {
                    'Key': 'SERVICE',
                    'Values': ['Amazon Bedrock']
                }
            },
            Metrics=['UnblendedCost']
        )

        total = Decimal('0')
        for result in response.get('ResultsByTime', []):
            amount = result.get('Total', {}).get('UnblendedCost', {}).get('Amount', '0')
            total += Decimal(str(amount))

        return total

    except ce_client.exceptions.DataUnavailableException:
        logger.warning("Cost Explorer data not available yet")
        return Decimal('0')


def _get_internal_tracking_total(start_date, end_date):
    """Sum costs from internal usage_tracking DynamoDB table for the date range"""
    if not USAGE_TRACKING_TABLE:
        logger.warning("USAGE_TRACKING_TABLE not configured")
        return Decimal('0')

    table = dynamodb.Table(USAGE_TRACKING_TABLE)

    # Convert dates to epoch for filtering
    start_epoch = int(datetime.strptime(start_date, '%Y-%m-%d').timestamp())
    end_epoch = int(datetime.strptime(end_date, '%Y-%m-%d').timestamp())

    total = Decimal('0')
    scan_kwargs = {
        'FilterExpression': Attr('created_epoch').between(start_epoch, end_epoch),
        'ProjectionExpression': 'cost_usd'
    }

    while True:
        response = table.scan(**scan_kwargs)
        for item in response.get('Items', []):
            cost = item.get('cost_usd', Decimal('0'))
            if isinstance(cost, (int, float, str)):
                cost = Decimal(str(cost))
            total += cost

        last_key = response.get('LastEvaluatedKey')
        if not last_key:
            break
        scan_kwargs['ExclusiveStartKey'] = last_key

    return total


def _calculate_drift(ce_total, internal_total):
    """Calculate drift percentage between Cost Explorer and internal tracking"""
    if ce_total == 0 and internal_total == 0:
        return 0.0

    # Use the larger value as the denominator to avoid division by near-zero
    denominator = max(float(ce_total), float(internal_total))
    if denominator == 0:
        return 0.0

    drift = ((float(ce_total) - float(internal_total)) / denominator) * 100
    return round(drift, 2)


def _publish_drift_metric(drift_percent):
    """Publish cost reconciliation drift metric to CloudWatch"""
    cloudwatch_client.put_metric_data(
        Namespace=METRIC_NAMESPACE,
        MetricData=[{
            'MetricName': 'CostReconciliationDrift',
            'Dimensions': [
                {'Name': 'Environment', 'Value': ENVIRONMENT}
            ],
            'Value': abs(drift_percent),
            'Unit': 'Percent'
        }]
    )


def _send_drift_alert(ce_total, internal_total, drift_percent):
    """Send SNS alert when drift exceeds threshold"""
    if not OPERATIONAL_ALERTS_SNS_TOPIC_ARN:
        logger.warning("No SNS topic configured for drift alerts")
        return

    message = (
        f"Cost Reconciliation Drift Alert\\n"
        f"Environment: {ENVIRONMENT}\\n"
        f"Drift: {drift_percent:.2f}% (threshold: {DRIFT_THRESHOLD_PERCENT}%)\\n"
        f"Cost Explorer Total: ${float(ce_total):.4f}\\n"
        f"Internal Tracking Total: ${float(internal_total):.4f}\\n"
        f"Difference: ${abs(float(ce_total) - float(internal_total)):.4f}\\n"
        f"\\nAction Required: Investigate cost tracking discrepancy."
    )

    sns_client.publish(
        TopicArn=OPERATIONAL_ALERTS_SNS_TOPIC_ARN,
        Subject=f"[Bedrock Budgeteer] Cost Drift Alert: {drift_percent:.1f}%",
        Message=message
    )

    logger.info(f"Drift alert sent: {drift_percent:.2f}%")
'''
