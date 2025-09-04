"""
IAM Utilities Lambda Function
Handles IAM policy backup, modification, and restoration operations
"""


def get_iam_utilities_function_code() -> str:
    """Return the IAM utilities Lambda function code"""
    return """
import json
import os
import boto3
import logging
from datetime import datetime, timezone

# Initialize AWS clients
iam_client = boto3.client('iam')
dynamodb = boto3.resource('dynamodb')
ssm_client = boto3.client('ssm')

logger = logging.getLogger()
logger.setLevel(logging.INFO)

def lambda_handler(event, context):
    \"\"\"
    IAM utilities for Bedrock access suspension and restoration
    \"\"\"
    logger.info(f"IAM utilities called with action: {event.get('action')}")
    
    try:
        action = event.get('action')
        
        if action == 'apply_restriction':
            return apply_bedrock_restriction(event)
        elif action == 'restore_access':
            return restore_bedrock_access(event)
        elif action == 'validate_restrictions':
            return validate_restrictions(event)
        else:
            raise ValueError(f"Unknown action: {action}. Valid actions: apply_restriction, restore_access, validate_restrictions")
            
    except Exception as e:
        logger.error(f"Error in IAM utilities: {e}", exc_info=True)
        return {
            'statusCode': 500,
            'error': str(e),
            'action': event.get('action'),
            'principal_id': event.get('principal_id')
        }



def apply_bedrock_restriction(event):
    \"\"\"Apply Bedrock access suspension by detaching AWS managed policy\"\"\"
    principal_id = event.get('principal_id')
    account_type = event.get('account_type')
    
    if not principal_id or not account_type:
        raise ValueError("principal_id and account_type are required")
    restriction_level = event.get('restriction_level', 'full_suspension')
    
    logger.info(f"Applying {restriction_level} restriction to {principal_id}")
    
    try:
        # Only support full suspension now
        if restriction_level != 'full_suspension':
            raise ValueError(f"Only 'full_suspension' restriction level is supported. Got: {restriction_level}")
        
        # Apply the restriction (only support Bedrock API keys)
        if account_type == 'bedrock_api_key':
            # Full suspension: detach AWS managed policy
            detached_policy_arn = apply_full_suspension(principal_id)
        else:
            raise ValueError(f"Unsupported account type: {account_type}. Only 'bedrock_api_key' is supported.")
        
        # Tag the principal to track restriction state
        apply_restriction_tags(principal_id, account_type, restriction_level)
        
        result = {
            'statusCode': 200,
            'principal_id': principal_id,
            'restriction_level': restriction_level,
            'detached_policy_arn': detached_policy_arn,
            'timestamp': datetime.now(timezone.utc).isoformat()
        }
        
        return result
        
    except Exception as e:
        logger.error(f"Error applying restrictions to {principal_id}: {e}")
        raise





def apply_full_suspension(username):
    \"\"\"Apply full suspension by detaching AWS managed policy\"\"\"
    try:
        # Detach the AmazonBedrockLimitedAccess managed policy
        managed_policy_arn = "arn:aws:iam::aws:policy/AmazonBedrockLimitedAccess"
        
        iam_client.detach_user_policy(
            UserName=username,
            PolicyArn=managed_policy_arn
        )
        logger.info(f"Detached AmazonBedrockLimitedAccess policy from user {username}")
        
        # Store the detached policy ARN for restoration
        return managed_policy_arn
        
    except iam_client.exceptions.NoSuchEntityException:
        logger.warning(f"AmazonBedrockLimitedAccess policy was not attached to user {username}")
        return managed_policy_arn
    except Exception as e:
        logger.error(f"Error detaching AmazonBedrockLimitedAccess policy from user {username}: {e}")
        raise

def restore_bedrock_access(event):
    \"\"\"Restore Bedrock access by reattaching AWS managed policy\"\"\"
    principal_id = event.get('principal_id')
    account_type = event.get('account_type')
    
    if not principal_id or not account_type:
        raise ValueError("principal_id and account_type are required")
    
    logger.info(f"Restoring Bedrock access for {principal_id}")
    
    try:
        # Only support Bedrock API keys
        if account_type != 'bedrock_api_key':
            raise ValueError(f"Unsupported account type: {account_type}. Only 'bedrock_api_key' is supported.")
        
        # Reattach the AmazonBedrockLimitedAccess managed policy
        managed_policy_arn = "arn:aws:iam::aws:policy/AmazonBedrockLimitedAccess"
        
        iam_client.attach_user_policy(
            UserName=principal_id,
            PolicyArn=managed_policy_arn
        )
        logger.info(f"Reattached {managed_policy_arn} policy to user {principal_id}")
        
        # Remove restriction tags
        remove_restriction_tags(principal_id, account_type)
        
        return {
            'statusCode': 200,
            'principal_id': principal_id,
            'restored_policy_arn': managed_policy_arn,
            'timestamp': datetime.now(timezone.utc).isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error restoring access for {principal_id}: {e}")
        raise



def apply_restriction_tags(principal_id, account_type, restriction_level):
    \"\"\"Tag principal with restriction information\"\"\"
    tags = [
        {'Key': 'BedrockBudgeteerRestricted', 'Value': 'true'},
        {'Key': 'BedrockBudgeteerRestrictionLevel', 'Value': restriction_level},
        {'Key': 'BedrockBudgeteerRestrictionTimestamp', 'Value': datetime.now(timezone.utc).isoformat()}
    ]
    
    try:
        if account_type == 'bedrock_api_key':
            # Bedrock API keys are IAM users, use user tagging
            iam_client.tag_user(UserName=principal_id, Tags=tags)
        else:
            raise ValueError(f"Unsupported account type: {account_type}. Only 'bedrock_api_key' is supported.")
        
        logger.info(f"Applied restriction tags to {principal_id}")
    except Exception as e:
        logger.error(f"Error applying tags to {principal_id}: {e}")
        # Don't fail the operation for tagging errors



def remove_restriction_tags(principal_id, principal_type):
    \"\"\"Remove restriction tags\"\"\"
    restriction_tag_keys = [
        'BedrockBudgeteerRestricted',
        'BedrockBudgeteerRestrictionLevel', 
        'BedrockBudgeteerRestrictionTimestamp'
    ]
    
    try:
        if principal_type in ['user', 'bedrock_api_key']:
            # Bedrock API keys are IAM users, use user untagging
            iam_client.untag_user(UserName=principal_id, TagKeys=restriction_tag_keys)
        else:
            logger.error(f"Unsupported principal_type: {principal_type}. Only 'bedrock_api_key' is supported.")
            return
        
        logger.info(f"Removed restriction tags from {principal_id}")
    except Exception as e:
        logger.warning(f"Error removing tags from {principal_id}: {e}")

def validate_restrictions(event):
    \"\"\"Validate that restrictions are properly applied\"\"\"
    principal_id = event.get('principal_id')
    account_type = event.get('account_type')
    expected_level = event.get('restriction_level', 'full_suspension')
    
    if not principal_id or not account_type:
        raise ValueError("principal_id and account_type are required")
    
    logger.info(f"Validating restrictions for {principal_id}")
    
    try:
        # Only support full suspension validation
        if expected_level != 'full_suspension':
            raise ValueError(f"Only 'full_suspension' restriction level validation is supported. Got: {expected_level}")
        
        # Check if AWS managed policy is detached
        policy_detached = check_managed_policy_detached(principal_id, account_type)
        
        # Check for restriction tags
        has_tags = check_restriction_tags(principal_id, account_type)
        
        is_valid = policy_detached and has_tags
        
        return {
            'statusCode': 200,
            'principal_id': principal_id,
            'is_valid': is_valid,
            'policy_detached': policy_detached,
            'has_restriction_tags': has_tags,
            'expected_level': expected_level,
            'timestamp': datetime.now(timezone.utc).isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error validating restrictions for {principal_id}: {e}")
        raise

def check_managed_policy_detached(principal_id, account_type):
    \"\"\"Check if the AWS managed policy is detached (meaning user is suspended)\"\"\"
    try:
        if account_type != 'bedrock_api_key':
            logger.error(f"Unsupported account type: {account_type}. Only 'bedrock_api_key' is supported.")
            return False
        
        # Check if AmazonBedrockLimitedAccess policy is attached
        managed_policy_arn = "arn:aws:iam::aws:policy/AmazonBedrockLimitedAccess"
        
        try:
            response = iam_client.list_attached_user_policies(UserName=principal_id)
            attached_policies = [policy['PolicyArn'] for policy in response['AttachedPolicies']]
            
            # If the policy is NOT in the attached policies list, it's detached (suspended)
            is_detached = managed_policy_arn not in attached_policies
            
            logger.info(f"Policy {managed_policy_arn} detached status for {principal_id}: {is_detached}")
            return is_detached
            
        except iam_client.exceptions.NoSuchEntityException:
            logger.error(f"User {principal_id} not found")
            return False
        
    except Exception as e:
        logger.error(f"Error checking managed policy status for {principal_id}: {e}")
        return False

def check_restriction_tags(principal_id, account_type):
    \"\"\"Check if restriction tags are present\"\"\"
    try:
        if account_type == 'bedrock_api_key':
            # Bedrock API keys are IAM users, use user tag listing
            response = iam_client.list_user_tags(UserName=principal_id)
        else:
            logger.error(f"Unsupported account type: {account_type}. Only 'bedrock_api_key' is supported.")
            return False
        
        tag_keys = set(tag['Key'] for tag in response['Tags'])
        return 'BedrockBudgeteerRestricted' in tag_keys
        
    except Exception as e:
        logger.error(f"Error checking restriction tags for {principal_id}: {e}")
        return False
"""
