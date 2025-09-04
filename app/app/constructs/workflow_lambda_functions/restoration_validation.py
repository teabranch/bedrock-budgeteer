"""
Restoration Validation Lambda Function
Validates restoration requests and prerequisites
"""


def get_restoration_validation_function_code() -> str:
    """Return the restoration validation Lambda function code"""
    return """
import json
import os
import boto3
import logging
from datetime import datetime, timezone, timedelta

dynamodb = boto3.resource('dynamodb')
ssm = boto3.client('ssm')

logger = logging.getLogger()
logger.setLevel(logging.INFO)

def lambda_handler(event, context):
    \"\"\"
    Validate automatic restoration request based on refresh period
    \"\"\"
    logger.info(f"Automatic restoration validation: {json.dumps(event)}")
    
    try:
        principal_id = event.get('principal_id')
        if not principal_id:
            return {'statusCode': 400, 'error': 'principal_id required'}
        
        validation_type = event.get('validation_type', 'automatic_refresh')
        
        # Validate the automatic restoration request
        validation_result = validate_automatic_restoration_request(principal_id)
        
        if validation_result['is_valid']:
            # Update user status to indicate restoration in progress
            update_restoration_status(principal_id, 'automatic_restoration_in_progress')
        
        return {
            'statusCode': 200,
            'validation_result': validation_result,
            'principal_id': principal_id,
            'next_refresh_date': validation_result.get('next_refresh_date'),
            'timestamp': datetime.now(timezone.utc).isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error in restoration validation: {e}", exc_info=True)
        return {
            'statusCode': 500,
            'error': str(e),
            'validation_result': {
                'is_valid': False,
                'error': str(e)
            },
            'principal_id': event.get('principal_id')
        }

def validate_automatic_restoration_request(principal_id):
    \"\"\"Validate automatic restoration request based on refresh period\"\"\"
    validation_result = {
        'is_valid': False,
        'reasons': [],
        'user_exists': False,
        'refresh_period_reached': False,
        'next_refresh_date': None
    }
    
    try:
        # Check if user exists and get current state
        user_budgets_table = dynamodb.Table(os.environ['USER_BUDGETS_TABLE'])
        response = user_budgets_table.get_item(Key={'principal_id': principal_id})
        
        if 'Item' not in response:
            validation_result['reasons'].append('User budget entry not found')
            return validation_result
        
        validation_result['user_exists'] = True
        user_item = response['Item']
        
        # Check if user is actually suspended
        current_status = user_item.get('status', 'active')
        if current_status != 'suspended':
            validation_result['reasons'].append(f'User is not suspended (current status: {current_status})')
            return validation_result
        
        # Check if refresh period has been reached
        current_time = datetime.now(timezone.utc)
        budget_refresh_date_str = user_item.get('budget_refresh_date')
        
        if not budget_refresh_date_str:
            validation_result['reasons'].append('No budget refresh date found')
            return validation_result
        
        try:
            # Parse the refresh date
            refresh_date = datetime.fromisoformat(budget_refresh_date_str.replace('Z', '+00:00'))
            
            # Check if current time is past the refresh date
            if current_time >= refresh_date:
                validation_result['refresh_period_reached'] = True
                
                # Calculate next refresh date
                refresh_period_days = user_item.get('refresh_period_days', 30)
                next_refresh_date = current_time + timedelta(days=int(refresh_period_days))
                validation_result['next_refresh_date'] = next_refresh_date.isoformat()
            else:
                time_remaining = refresh_date - current_time
                validation_result['reasons'].append(f'Refresh period not reached. {time_remaining.days} days remaining until {refresh_date.isoformat()}')
                
        except (ValueError, TypeError) as e:
            logger.error(f"Error parsing refresh date {budget_refresh_date_str}: {e}")
            validation_result['reasons'].append(f'Invalid refresh date format: {budget_refresh_date_str}')
            return validation_result
        
        # Overall validation - only check if user exists, is suspended, and refresh period reached
        validation_result['is_valid'] = (
            validation_result['user_exists'] and
            validation_result['refresh_period_reached'] and
            current_status == 'suspended'
        )
        
        return validation_result
        
    except Exception as e:
        logger.error(f"Error validating automatic restoration request: {e}")
        validation_result['reasons'].append(f'Validation error: {str(e)}')
        return validation_result



def update_restoration_status(principal_id, status):
    \"\"\"Update user restoration status\"\"\"
    try:
        user_budgets_table = dynamodb.Table(os.environ['USER_BUDGETS_TABLE'])
        
        user_budgets_table.update_item(
            Key={'principal_id': principal_id},
            UpdateExpression='SET restoration_status = :status, restoration_start_epoch = :timestamp',
            ExpressionAttributeValues={
                ':status': status,
                ':timestamp': int(datetime.now(timezone.utc).timestamp())
            }
        )
        
        logger.info(f"Updated restoration status for {principal_id}: {status}")
        
    except Exception as e:
        logger.error(f"Error updating restoration status: {e}")
        raise
"""
