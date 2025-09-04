"""
Metrics Publisher
Publishes custom CloudWatch metrics
"""
import boto3
import logging
from typing import Dict, Optional
from datetime import datetime, timezone

logger = logging.getLogger()

# AWS clients will be initialized lazily


class MetricsPublisher:
    """Publishes custom CloudWatch metrics"""
    
    @staticmethod
    def publish_budget_metric(metric_name: str, value: float, unit: str = 'None', 
                            dimensions: Optional[Dict[str, str]] = None):
        """Publish a budget-related metric to CloudWatch"""
        try:
            metric_data = {
                'MetricName': metric_name,
                'Value': value,
                'Unit': unit,
                'Timestamp': datetime.now(timezone.utc)
            }
            
            if dimensions:
                metric_data['Dimensions'] = [
                    {'Name': k, 'Value': v} for k, v in dimensions.items()
                ]
            
            cloudwatch = boto3.client('cloudwatch')
            cloudwatch.put_metric_data(
                Namespace='BedrockBudgeteer',
                MetricData=[metric_data]
            )
        except Exception as e:
            logger.error(f"Failed to publish metric {metric_name}: {e}")
