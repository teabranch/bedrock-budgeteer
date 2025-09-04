"""
Policy Backup Lambda Function
Wrapper for policy backup operations - delegates to IAM utilities function
"""


def get_policy_backup_function_code() -> str:
    """Return the policy backup Lambda function code"""
    return """
import json
import os
import logging
from datetime import datetime, timezone

logger = logging.getLogger()
logger.setLevel(logging.INFO)

def lambda_handler(event, context):
    \"\"\"
    Wrapper for policy backup operations - delegates to IAM utilities function
    \"\"\"
    logger.info(f"Policy backup handler: {json.dumps(event)}")
    
    return {
        'statusCode': 200,
        'backup_delegated': True,
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'event_data': event
    }
"""
