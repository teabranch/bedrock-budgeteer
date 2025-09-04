"""
Event Publisher
Publishes events to EventBridge
"""
import json
import boto3
import logging
from typing import Dict, Any
from datetime import datetime, timezone

logger = logging.getLogger()

# AWS clients will be initialized lazily


class EventPublisher:
    """Publishes events to EventBridge"""
    
    @staticmethod
    def publish_budget_event(event_type: str, detail: Dict[str, Any]):
        """Publish a budget-related event to EventBridge"""
        try:
            events = boto3.client('events')
            events.put_events(
                Entries=[
                    {
                        'Source': 'bedrock-budgeteer',
                        'DetailType': event_type,
                        'Detail': json.dumps(detail, default=str),
                        'Time': datetime.now(timezone.utc)
                    }
                ]
            )
        except Exception as e:
            logger.error(f"Failed to publish event {event_type}: {e}")
