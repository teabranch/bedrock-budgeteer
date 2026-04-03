"""
AgentCore IAM Utilities Lambda Function
Handles policy snapshot, stripping, and restoration for AgentCore execution roles.
"""


def get_agentcore_iam_utilities_function_code() -> str:
    """Return the AgentCore IAM utilities Lambda function code"""
    return '''
import json
import os
import boto3
import logging
from datetime import datetime, timezone

iam_client = boto3.client('iam')
dynamodb = boto3.resource('dynamodb')

logger = logging.getLogger()
logger.setLevel(logging.INFO)

def lambda_handler(event, context):
    """AgentCore IAM utilities for suspension and restoration"""
    logger.info(f"AgentCore IAM utilities called with action: {event.get('action')}")

    try:
        action = event.get('action')

        if action == 'apply_restriction':
            return apply_agentcore_restriction(event)
        elif action == 'restore_access':
            return restore_agentcore_access(event)
        elif action == 'validate_restrictions':
            return validate_agentcore_restrictions(event)
        else:
            raise ValueError(f"Unknown action: {action}")

    except Exception as e:
        logger.error(f"Error in AgentCore IAM utilities: {e}", exc_info=True)
        return {'statusCode': 500, 'error': str(e), 'action': event.get('action')}


def apply_agentcore_restriction(event):
    """Suspend an AgentCore runtime by snapshotting and stripping its execution role policies"""
    runtime_id = event.get('runtime_id')
    role_arn = event.get('role_arn')
    account_type = event.get('account_type', 'agentcore_runtime')

    if not runtime_id or not role_arn:
        raise ValueError("runtime_id and role_arn are required")

    if account_type != 'agentcore_runtime':
        raise ValueError(f"Unsupported account_type: {account_type}")

    role_name = role_arn.split('/')[-1]
    logger.info(f"Applying restriction to AgentCore runtime {runtime_id}, role: {role_name}")

    snapshot = snapshot_role_policies(role_name)

    table = dynamodb.Table(os.environ['AGENTCORE_BUDGETS_TABLE'])
    table.update_item(
        Key={'runtime_id': runtime_id},
        UpdateExpression='SET policy_snapshot = :snapshot, snapshot_timestamp = :ts',
        ExpressionAttributeValues={
            ':snapshot': json.dumps(snapshot),
            ':ts': datetime.now(timezone.utc).isoformat()
        }
    )

    strip_role_policies(role_name, snapshot)

    deny_all_policy = {
        "Version": "2012-10-17",
        "Statement": [{
            "Effect": "Deny",
            "Action": "*",
            "Resource": "*"
        }]
    }
    iam_client.put_role_policy(
        RoleName=role_name,
        PolicyName='BedrockBudgeteerDenyAll',
        PolicyDocument=json.dumps(deny_all_policy)
    )

    apply_restriction_tags(role_name)

    return {
        'statusCode': 200,
        'runtime_id': runtime_id,
        'role_name': role_name,
        'policies_stripped': len(snapshot.get('managed_policies', [])) + len(snapshot.get('inline_policies', {})),
        'timestamp': datetime.now(timezone.utc).isoformat()
    }


def snapshot_role_policies(role_name):
    """Snapshot all policies attached to a role"""
    snapshot = {'managed_policies': [], 'inline_policies': {}}

    paginator = iam_client.get_paginator('list_attached_role_policies')
    for page in paginator.paginate(RoleName=role_name):
        for policy in page['AttachedPolicies']:
            snapshot['managed_policies'].append(policy['PolicyArn'])

    paginator = iam_client.get_paginator('list_role_policies')
    for page in paginator.paginate(RoleName=role_name):
        for policy_name in page['PolicyNames']:
            if policy_name == 'BedrockBudgeteerDenyAll':
                continue
            response = iam_client.get_role_policy(RoleName=role_name, PolicyName=policy_name)
            snapshot['inline_policies'][policy_name] = response['PolicyDocument']

    logger.info(f"Snapshot for {role_name}: {len(snapshot['managed_policies'])} managed, "
                f"{len(snapshot['inline_policies'])} inline policies")
    return snapshot


def strip_role_policies(role_name, snapshot):
    """Remove all policies from a role"""
    for policy_arn in snapshot['managed_policies']:
        try:
            iam_client.detach_role_policy(RoleName=role_name, PolicyArn=policy_arn)
            logger.info(f"Detached managed policy {policy_arn} from {role_name}")
        except iam_client.exceptions.NoSuchEntityException:
            logger.warning(f"Policy {policy_arn} already detached from {role_name}")

    for policy_name in snapshot['inline_policies']:
        try:
            iam_client.delete_role_policy(RoleName=role_name, PolicyName=policy_name)
            logger.info(f"Deleted inline policy {policy_name} from {role_name}")
        except iam_client.exceptions.NoSuchEntityException:
            logger.warning(f"Inline policy {policy_name} already removed from {role_name}")


def restore_agentcore_access(event):
    """Restore an AgentCore runtime's execution role policies from snapshot"""
    runtime_id = event.get('runtime_id')
    role_arn = event.get('role_arn')
    account_type = event.get('account_type', 'agentcore_runtime')

    if not runtime_id or not role_arn:
        raise ValueError("runtime_id and role_arn are required")

    if account_type != 'agentcore_runtime':
        raise ValueError(f"Unsupported account_type: {account_type}")

    role_name = role_arn.split('/')[-1]
    logger.info(f"Restoring access for AgentCore runtime {runtime_id}, role: {role_name}")

    table = dynamodb.Table(os.environ['AGENTCORE_BUDGETS_TABLE'])
    response = table.get_item(Key={'runtime_id': runtime_id})
    item = response.get('Item', {})
    snapshot_json = item.get('policy_snapshot')

    if not snapshot_json:
        raise ValueError(f"No policy snapshot found for runtime {runtime_id}")

    snapshot = json.loads(snapshot_json)

    try:
        iam_client.delete_role_policy(RoleName=role_name, PolicyName='BedrockBudgeteerDenyAll')
        logger.info(f"Removed BedrockBudgeteerDenyAll from {role_name}")
    except iam_client.exceptions.NoSuchEntityException:
        logger.warning(f"BedrockBudgeteerDenyAll not found on {role_name}")

    for policy_arn in snapshot.get('managed_policies', []):
        try:
            iam_client.attach_role_policy(RoleName=role_name, PolicyArn=policy_arn)
            logger.info(f"Reattached managed policy {policy_arn} to {role_name}")
        except Exception as e:
            logger.error(f"Error reattaching {policy_arn}: {e}")
            raise

    for policy_name, policy_doc in snapshot.get('inline_policies', {}).items():
        try:
            iam_client.put_role_policy(
                RoleName=role_name,
                PolicyName=policy_name,
                PolicyDocument=json.dumps(policy_doc) if isinstance(policy_doc, dict) else policy_doc
            )
            logger.info(f"Recreated inline policy {policy_name} on {role_name}")
        except Exception as e:
            logger.error(f"Error recreating {policy_name}: {e}")
            raise

    remove_restriction_tags(role_name)

    table.update_item(
        Key={'runtime_id': runtime_id},
        UpdateExpression='REMOVE policy_snapshot, snapshot_timestamp'
    )

    return {
        'statusCode': 200,
        'runtime_id': runtime_id,
        'role_name': role_name,
        'policies_restored': len(snapshot.get('managed_policies', [])) + len(snapshot.get('inline_policies', {})),
        'timestamp': datetime.now(timezone.utc).isoformat()
    }


def validate_agentcore_restrictions(event):
    """Validate that restrictions are properly applied to an AgentCore runtime role"""
    runtime_id = event.get('runtime_id')
    role_arn = event.get('role_arn')
    account_type = event.get('account_type', 'agentcore_runtime')

    if not runtime_id or not role_arn:
        raise ValueError("runtime_id and role_arn are required")

    if account_type != 'agentcore_runtime':
        raise ValueError(f"Unsupported account_type: {account_type}")

    role_name = role_arn.split('/')[-1]

    has_deny_all = False
    try:
        iam_client.get_role_policy(RoleName=role_name, PolicyName='BedrockBudgeteerDenyAll')
        has_deny_all = True
    except iam_client.exceptions.NoSuchEntityException:
        has_deny_all = False

    has_tags = False
    try:
        response = iam_client.list_role_tags(RoleName=role_name)
        tag_keys = {tag['Key'] for tag in response.get('Tags', [])}
        has_tags = 'BedrockBudgeteerRestricted' in tag_keys
    except Exception as e:
        logger.error(f"Error checking tags for {role_name}: {e}")

    is_valid = has_deny_all and has_tags

    return {
        'statusCode': 200,
        'runtime_id': runtime_id,
        'is_valid': is_valid,
        'has_deny_all_policy': has_deny_all,
        'has_restriction_tags': has_tags,
        'timestamp': datetime.now(timezone.utc).isoformat()
    }


def apply_restriction_tags(role_name):
    """Tag role with restriction information"""
    tags = [
        {'Key': 'BedrockBudgeteerRestricted', 'Value': 'true'},
        {'Key': 'BedrockBudgeteerRestrictionLevel', 'Value': 'full_suspension'},
        {'Key': 'BedrockBudgeteerRestrictionTimestamp', 'Value': datetime.now(timezone.utc).isoformat()}
    ]
    try:
        iam_client.tag_role(RoleName=role_name, Tags=tags)
        logger.info(f"Applied restriction tags to role {role_name}")
    except Exception as e:
        logger.error(f"Error applying tags to role {role_name}: {e}")


def remove_restriction_tags(role_name):
    """Remove restriction tags from role"""
    tag_keys = [
        'BedrockBudgeteerRestricted',
        'BedrockBudgeteerRestrictionLevel',
        'BedrockBudgeteerRestrictionTimestamp'
    ]
    try:
        iam_client.untag_role(RoleName=role_name, TagKeys=tag_keys)
        logger.info(f"Removed restriction tags from role {role_name}")
    except Exception as e:
        logger.warning(f"Error removing tags from role {role_name}: {e}")
'''
