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
Hi there! 👋

Your Bedrock usage has reached your budget limit. 

You have {grace_minutes} minutes to wrap up any current work before access is temporarily paused. Your access will automatically return when your budget refreshes, or you can contact your administrator if you need immediate assistance.

Thanks for being mindful of your usage!

The Bedrock Team
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
            Subject=f"Bedrock Budget Reached - {grace_minutes} minutes remaining"
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
Quick reminder! ⏰

You have {remaining_minutes} minutes left before your Bedrock access pauses.

Please finish up any current work. Need more time? Just reach out to your administrator.

The Bedrock Team
\"\"\"
    
    try:
        # Get SNS topic ARN from environment variable
        operational_alerts_topic_arn = os.environ.get('OPERATIONAL_ALERTS_TOPIC_ARN')
        if not operational_alerts_topic_arn:
            raise ValueError("OPERATIONAL_ALERTS_TOPIC_ARN environment variable not set")
        
        sns.publish(
            TopicArn=operational_alerts_topic_arn,
            Message=message,
            Subject=f"Bedrock Access - {remaining_minutes} minutes remaining"
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
Bedrock Access Paused 🛑

Your budget limit has been reached and access is now paused.

Don't worry - your access will automatically return when your budget refreshes! If you need access sooner, just contact your administrator.

Thanks for your understanding!

The Bedrock Team
\"\"\"
    
    try:
        # Get SNS topic ARN from environment variable
        high_severity_topic_arn = os.environ.get('HIGH_SEVERITY_TOPIC_ARN')
        if not high_severity_topic_arn:
            raise ValueError("HIGH_SEVERITY_TOPIC_ARN environment variable not set")
        
        sns.publish(
            TopicArn=high_severity_topic_arn,
            Message=message,
            Subject=f"Bedrock Access Paused - Budget Limit Reached"
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
Welcome back! 🎉

Your Bedrock access has been restored and you're all set to continue your work.

Your budget has been reset and you can now use Bedrock services again. Happy creating!

The Bedrock Team
\"\"\"
    
    try:
        # Get SNS topic ARN from environment variable
        operational_alerts_topic_arn = os.environ.get('OPERATIONAL_ALERTS_TOPIC_ARN')
        if not operational_alerts_topic_arn:
            raise ValueError("OPERATIONAL_ALERTS_TOPIC_ARN environment variable not set")
        
        sns.publish(
            TopicArn=operational_alerts_topic_arn,
            Message=message,
            Subject=f"Bedrock Access Restored - You're back!"
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
Good news! 🌟

Your budget has refreshed and your Bedrock access is back!

You can now resume using Bedrock services with a fresh budget. We've reset your spending counter to $0.

Happy creating!

The Bedrock Team
\"\"\"
    
    try:
        # Get SNS topic ARN from environment variable
        operational_alerts_topic_arn = os.environ.get('OPERATIONAL_ALERTS_TOPIC_ARN')
        if not operational_alerts_topic_arn:
            raise ValueError("OPERATIONAL_ALERTS_TOPIC_ARN environment variable not set")
        
        sns.publish(
            TopicArn=operational_alerts_topic_arn,
            Message=message,
            Subject=f"Budget Refreshed - Bedrock Access is Back!"
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
