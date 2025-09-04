"""
Grace Period Notifications Lambda Function
Handles grace period notifications and countdown operations
"""


def get_grace_period_function_code() -> str:
    """Return the grace period notifications Lambda function code"""
    return """
import json
import os
import boto3
import logging
from datetime import datetime, timezone, timedelta

sns = boto3.client('sns')
events = boto3.client('events')

logger = logging.getLogger()
logger.setLevel(logging.INFO)

def lambda_handler(event, context):
    \"\"\"
    Handle grace period notifications and countdown
    \"\"\"
    logger.info(f"Grace period handler called: {json.dumps(event)}")
    
    try:
        principal_id = event.get('principal_id')
        if not principal_id:
            return {'statusCode': 400, 'error': 'principal_id required'}
        grace_period_seconds = event.get('grace_period_seconds', 300)  # 5 minutes default
        notification_type = event.get('notification_type', 'initial')
        
        if notification_type == 'initial':
            return send_initial_grace_notification(principal_id, grace_period_seconds)
        elif notification_type == 'countdown':
            return send_countdown_notification(principal_id, event.get('remaining_seconds', 0))
        elif notification_type == 'final':
            return send_final_warning(principal_id)
        elif notification_type == 'restoration_complete':
            return send_restoration_notification(principal_id)
        elif notification_type == 'automatic_restoration_complete':
            return send_automatic_restoration_notification(principal_id)
        else:
            raise ValueError(f"Unknown notification type: {notification_type}")
            
    except Exception as e:
        logger.error(f"Error in grace period handler: {e}", exc_info=True)
        return {
            'statusCode': 500,
            'error': str(e),
            'principal_id': event.get('principal_id')
        }

def send_initial_grace_notification(principal_id, grace_period_seconds):
    \"\"\"Send initial grace period notification\"\"\"
    grace_minutes = grace_period_seconds // 60
    deadline = datetime.now(timezone.utc) + timedelta(seconds=grace_period_seconds)
    
    message = f\"\"\"
Budget Exceeded - Grace Period Started

User: {principal_id}
Grace Period: {grace_minutes} minutes
Deadline: {deadline.strftime('%Y-%m-%d %H:%M:%S UTC')}

Your AWS Bedrock access budget has been exceeded. 
You have {grace_minutes} minutes to review your usage before access restrictions are applied.

Access will be progressively restricted in the following stages:
1. Expensive models (Claude-3 Opus, Claude-3.5 Sonnet)
2. All model invocations
3. Full Bedrock access suspension

If you believe this is an error, please contact your administrator immediately.
\"\"\"
    
    try:
        # Get SNS topic ARN from environment variable
        high_severity_topic_arn = os.environ.get('HIGH_SEVERITY_TOPIC_ARN')
        if not high_severity_topic_arn:
            raise ValueError("HIGH_SEVERITY_TOPIC_ARN environment variable not set")
        
        # Publish to SNS (high severity topic)
        sns.publish(
            TopicArn=high_severity_topic_arn,
            Message=message,
            Subject=f"Bedrock Budget Exceeded - Grace Period: {principal_id}"
        )
        
        # Publish event for audit trail
        events.put_events(
            Entries=[{
                'Source': 'bedrock-budgeteer',
                'DetailType': 'Grace Period Started',
                'Detail': json.dumps({
                    'principal_id': principal_id,
                    'grace_period_seconds': grace_period_seconds,
                    'deadline': deadline.isoformat(),
                    'timestamp': datetime.now(timezone.utc).isoformat()
                })
            }]
        )
        
        return {
            'statusCode': 200,
            'principal_id': principal_id,
            'notification_sent': True,
            'deadline': deadline.isoformat(),
            'grace_period_seconds': grace_period_seconds
        }
        
    except Exception as e:
        logger.error(f"Error sending initial grace notification: {e}")
        raise

def send_countdown_notification(principal_id, remaining_seconds):
    \"\"\"Send countdown notification\"\"\"
    remaining_minutes = remaining_seconds // 60
    
    message = f\"\"\"
Budget Grace Period - {remaining_minutes} Minutes Remaining

User: {principal_id}
Time Remaining: {remaining_minutes} minutes

Your Bedrock access budget grace period is ending soon.
Access restrictions will be applied automatically when the grace period expires.

Contact your administrator if you need assistance.
\"\"\"
    
    try:
        # Get SNS topic ARN from environment variable
        operational_alerts_topic_arn = os.environ.get('OPERATIONAL_ALERTS_TOPIC_ARN')
        if not operational_alerts_topic_arn:
            raise ValueError("OPERATIONAL_ALERTS_TOPIC_ARN environment variable not set")
        
        sns.publish(
            TopicArn=operational_alerts_topic_arn,
            Message=message,
            Subject=f"Bedrock Budget Grace Period Ending: {principal_id}"
        )
        
        return {
            'statusCode': 200,
            'principal_id': principal_id,
            'notification_sent': True,
            'remaining_seconds': remaining_seconds
        }
        
    except Exception as e:
        logger.error(f"Error sending countdown notification: {e}")
        raise

def send_final_warning(principal_id):
    \"\"\"Send final warning before suspension\"\"\"
    message = f\"\"\"
Budget Grace Period Expired - Implementing Restrictions

User: {principal_id}

The grace period for budget violation has expired.
Bedrock access restrictions are now being implemented.

Stage 1: Expensive model access will be restricted first.
Further restrictions may follow based on configuration.

Contact your administrator for budget increase or restoration procedures.
\"\"\"
    
    try:
        # Get SNS topic ARN from environment variable
        high_severity_topic_arn = os.environ.get('HIGH_SEVERITY_TOPIC_ARN')
        if not high_severity_topic_arn:
            raise ValueError("HIGH_SEVERITY_TOPIC_ARN environment variable not set")
        
        sns.publish(
            TopicArn=high_severity_topic_arn,
            Message=message,
            Subject=f"Bedrock Access Restrictions Implemented: {principal_id}"
        )
        
        events.put_events(
            Entries=[{
                'Source': 'bedrock-budgeteer',
                'DetailType': 'Grace Period Expired',
                'Detail': json.dumps({
                    'principal_id': principal_id,
                    'timestamp': datetime.now(timezone.utc).isoformat(),
                    'action': 'implementing_restrictions'
                })
            }]
        )
        
        return {
            'statusCode': 200,
            'principal_id': principal_id,
            'notification_sent': True,
            'action': 'restrictions_starting'
        }
        
    except Exception as e:
        logger.error(f"Error sending final warning: {e}")
        raise

def send_restoration_notification(principal_id):
    \"\"\"Send notification when user access has been restored\"\"\"
    message = f\"\"\"
Bedrock Access Restored

User: {principal_id}

Your AWS Bedrock access has been successfully restored.
All previous access restrictions have been removed.

Your budget tracking has been reset and normal access is now available.

If you have any questions, please contact your administrator.
\"\"\"
    
    try:
        # Get SNS topic ARN from environment variable
        operational_alerts_topic_arn = os.environ.get('OPERATIONAL_ALERTS_TOPIC_ARN')
        if not operational_alerts_topic_arn:
            raise ValueError("OPERATIONAL_ALERTS_TOPIC_ARN environment variable not set")
        
        sns.publish(
            TopicArn=operational_alerts_topic_arn,
            Message=message,
            Subject=f"Bedrock Access Restored: {principal_id}"
        )
        
        events.put_events(
            Entries=[{
                'Source': 'bedrock-budgeteer',
                'DetailType': 'User Access Restored Notification',
                'Detail': json.dumps({
                    'principal_id': principal_id,
                    'timestamp': datetime.now(timezone.utc).isoformat(),
                    'action': 'access_restored'
                })
            }]
        )
        
        return {
            'statusCode': 200,
            'principal_id': principal_id,
            'notification_sent': True,
            'action': 'restoration_notified'
        }
        
    except Exception as e:
        logger.error(f"Error sending restoration notification: {e}")
        raise

def send_automatic_restoration_notification(principal_id):
    \"\"\"Send automatic restoration complete notification\"\"\"
    message = f\"\"\"
Budget Period Refreshed - Access Automatically Restored

User: {principal_id}
Action: Automatic restoration completed
Budget Period: Reset
Timestamp: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}

Your budget refresh period has been reached and your Bedrock access has been automatically restored.

Your spending counter has been reset to $0.00 and you can now resume using Amazon Bedrock services within your budget limits.

Please monitor your usage to avoid future suspensions.

Best regards,
Bedrock Budgeteer System
\"\"\"
    
    try:
        # Get SNS topic ARN from environment variable
        operational_alerts_topic_arn = os.environ.get('OPERATIONAL_ALERTS_TOPIC_ARN')
        if not operational_alerts_topic_arn:
            raise ValueError("OPERATIONAL_ALERTS_TOPIC_ARN environment variable not set")
        
        sns.publish(
            TopicArn=operational_alerts_topic_arn,
            Message=message,
            Subject=f"Bedrock Budget Refreshed - Access Restored: {principal_id}"
        )
        
        events.put_events(
            Entries=[{
                'Source': 'bedrock-budgeteer',
                'DetailType': 'User Access Automatically Restored Notification',
                'Detail': json.dumps({
                    'principal_id': principal_id,
                    'timestamp': datetime.now(timezone.utc).isoformat(),
                    'action': 'automatic_restoration_notified',
                    'restoration_type': 'budget_refresh_period'
                })
            }]
        )
        
        return {
            'statusCode': 200,
            'principal_id': principal_id,
            'notification_sent': True,
            'action': 'automatic_restoration_notified'
        }
        
    except Exception as e:
        logger.error(f"Error sending automatic restoration notification: {e}")
        raise
"""
