"""
Cost Allocation Sync Lambda Function Code
Daily Lambda that queries AWS Cost Explorer for Bedrock costs grouped by cost allocation tags,
then publishes custom CloudWatch metrics for dashboard visualization.
"""


def get_cost_allocation_sync_function_code() -> str:
    """Return the inline Lambda function code for cost allocation sync"""
    return '''
import os
import json
import logging
from datetime import datetime, timedelta
from decimal import Decimal

import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

ce_client = boto3.client('ce')
cloudwatch_client = boto3.client('cloudwatch')

METRIC_NAMESPACE = 'BedrockBudgeteer/CostAllocation'
ENVIRONMENT = os.environ.get('ENVIRONMENT', 'production')


def lambda_handler(event, context):
    """Query Cost Explorer for Bedrock costs and publish CloudWatch metrics"""
    logger.info("Starting cost allocation sync")

    end_date = datetime.utcnow().strftime('%Y-%m-%d')
    start_date = (datetime.utcnow() - timedelta(days=7)).strftime('%Y-%m-%d')

    time_period = {'Start': start_date, 'End': end_date}
    bedrock_filter = {
        'Dimensions': {
            'Key': 'SERVICE',
            'Values': ['Amazon Bedrock']
        }
    }

    try:
        # Cost Explorer allows max 2 group-by dimensions per request
        # Make separate calls for each grouping
        _sync_cost_by_tag(time_period, bedrock_filter, 'BedrockBudgeteer:Team', 'CostByTeam')
        _sync_cost_by_tag(time_period, bedrock_filter, 'BedrockBudgeteer:Purpose', 'CostByPurpose')
        _sync_cost_by_tag(time_period, bedrock_filter, 'BedrockBudgeteer:BudgetTier', 'CostByTier')
        _sync_total_cost(time_period, bedrock_filter)

        logger.info("Cost allocation sync completed successfully")
        return {'statusCode': 200, 'body': 'Sync completed'}

    except Exception as e:
        logger.error(f"Cost allocation sync failed: {str(e)}")
        raise


def _sync_cost_by_tag(time_period, cost_filter, tag_key, metric_name):
    """Query Cost Explorer grouped by a specific tag and publish metrics"""
    try:
        response = ce_client.get_cost_and_usage(
            TimePeriod=time_period,
            Granularity='DAILY',
            Filter=cost_filter,
            GroupBy=[{'Type': 'TAG', 'Key': tag_key}],
            Metrics=['UnblendedCost']
        )

        metric_data = []
        for result in response.get('ResultsByTime', []):
            timestamp = datetime.strptime(result['TimePeriod']['Start'], '%Y-%m-%d')
            for group in result.get('Groups', []):
                tag_value = group['Keys'][0].split('$')[-1] if '$' in group['Keys'][0] else group['Keys'][0]
                if not tag_value:
                    tag_value = 'untagged'
                cost = float(group['Metrics']['UnblendedCost']['Amount'])

                metric_data.append({
                    'MetricName': metric_name,
                    'Dimensions': [
                        {'Name': 'Environment', 'Value': ENVIRONMENT},
                        {'Name': tag_key.split(':')[-1], 'Value': tag_value}
                    ],
                    'Timestamp': timestamp,
                    'Value': cost,
                    'Unit': 'None'
                })

        if metric_data:
            # CloudWatch PutMetricData allows max 1000 metric data points per call
            for i in range(0, len(metric_data), 1000):
                cloudwatch_client.put_metric_data(
                    Namespace=METRIC_NAMESPACE,
                    MetricData=metric_data[i:i + 1000]
                )
            logger.info(f"Published {len(metric_data)} {metric_name} metrics")
        else:
            logger.info(f"No data found for {tag_key}")

    except ce_client.exceptions.DataUnavailableException:
        logger.warning(f"Cost data not yet available for {tag_key}")
    except Exception as e:
        logger.error(f"Failed to sync {metric_name}: {str(e)}")
        raise


def _sync_total_cost(time_period, cost_filter):
    """Query total Bedrock cost and publish metric"""
    try:
        response = ce_client.get_cost_and_usage(
            TimePeriod=time_period,
            Granularity='DAILY',
            Filter=cost_filter,
            Metrics=['UnblendedCost']
        )

        metric_data = []
        for result in response.get('ResultsByTime', []):
            timestamp = datetime.strptime(result['TimePeriod']['Start'], '%Y-%m-%d')
            total = float(result.get('Total', {}).get('UnblendedCost', {}).get('Amount', 0))

            metric_data.append({
                'MetricName': 'TotalBedrockCost',
                'Dimensions': [
                    {'Name': 'Environment', 'Value': ENVIRONMENT}
                ],
                'Timestamp': timestamp,
                'Value': total,
                'Unit': 'None'
            })

        if metric_data:
            cloudwatch_client.put_metric_data(
                Namespace=METRIC_NAMESPACE,
                MetricData=metric_data
            )
            logger.info(f"Published {len(metric_data)} TotalBedrockCost metrics")

    except ce_client.exceptions.DataUnavailableException:
        logger.warning("Total cost data not yet available")
    except Exception as e:
        logger.error(f"Failed to sync total cost: {str(e)}")
        raise
'''
