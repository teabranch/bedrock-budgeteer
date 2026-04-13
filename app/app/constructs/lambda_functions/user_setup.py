"""
User Setup Lambda Function
Process CloudTrail IAM events to initialize Bedrock API key budgets.
Detects CDK-provisioned vs rogue keys and enforces tagging/budget policies.
"""


def get_user_setup_function_code() -> str:
    """Get the Lambda function code for user setup"""
    return '''
# IAM and SNS clients are not in shared utilities — initialize here
iam_client = boto3.client('iam')
sns_client = boto3.client('sns')


def lambda_handler(event, context):
    """
    Process CloudTrail IAM events to initialize Bedrock API key budgets.

    Monitors events: CreateUser, CreateServiceSpecificCredential,
    AttachUserPolicy, PutUserPolicy, TagUser, UntagUser.
    Only acts on userNames starting with BedrockAPIKey-.
    """
    logger.info(f"Processing user setup event: {json.dumps(event, default=str)}")

    try:
        if 'detail' not in event:
            logger.error("Invalid event format - missing detail")
            return {'statusCode': 400, 'body': 'Invalid event format'}

        detail = event.get('detail', {})
        event_name = detail.get('eventName')

        principal_id = _extract_principal_id(event_name, detail)
        if principal_id is None:
            return {'statusCode': 200, 'body': 'Event ignored - not relevant'}

        if not principal_id.startswith('BedrockAPIKey-'):
            logger.info(f"Ignoring non-Bedrock API key user: {principal_id}")
            return {'statusCode': 200, 'body': 'Event ignored - not a Bedrock API key'}

        return _process_bedrock_api_key(principal_id, detail, context)

    except Exception as e:
        logger.error(f"Error processing user setup event: {e}", exc_info=True)
        MetricsPublisher.publish_budget_metric(
            'UserSetupErrors',
            1.0,
            'Count',
            {'Environment': os.environ.get('ENVIRONMENT', 'unknown')}
        )
        raise


def _extract_principal_id(event_name, detail):
    """Extract the target userName from the CloudTrail event detail.

    Returns the userName if the event is relevant, or None to skip.
    """
    response_elements = detail.get('responseElements', {})
    request_parameters = detail.get('requestParameters', {})

    if event_name == 'CreateUser' and response_elements:
        user_info = response_elements.get('user', {})
        return user_info.get('userName', '')

    if event_name == 'CreateServiceSpecificCredential':
        return request_parameters.get('userName', '')

    if event_name in ('AttachUserPolicy', 'PutUserPolicy', 'TagUser', 'UntagUser'):
        return request_parameters.get('userName') or detail.get('userIdentity', {}).get('userName', '')

    logger.info(f"Ignoring event type: {event_name}")
    return None


def _process_bedrock_api_key(principal_id, event_detail, context):
    """Orchestrate budget registration for a Bedrock API key."""
    user_budgets_table = dynamodb.Table(os.environ['USER_BUDGETS_TABLE'])
    event_name = event_detail.get('eventName', '')

    # Idempotency: check if budget already exists
    existing_item = _get_existing_budget(user_budgets_table, principal_id)
    if existing_item is not None:
        if event_name in ('TagUser', 'UntagUser'):
            _handle_tag_change(principal_id, event_detail, user_budgets_table)
            return {'statusCode': 200, 'body': 'Tag change processed'}
        logger.info(f"Budget already exists for {principal_id}")
        return {'statusCode': 200, 'body': 'Budget already exists'}

    provisioning_info = _check_provisioning_status(principal_id, event_detail)
    _ensure_global_api_key_pool(user_budgets_table)
    _register_key_budget(principal_id, provisioning_info, user_budgets_table)

    logger.info(f"Successfully initialized budget for {principal_id}")
    return {'statusCode': 200, 'body': 'Budget initialized successfully'}


def _get_existing_budget(table, principal_id):
    """Return the existing budget item or None."""
    try:
        response = table.get_item(Key={'principal_id': principal_id})
        return response.get('Item')
    except Exception as e:
        logger.error(f"Error checking existing budget for {principal_id}: {e}")
        return None


def _check_provisioning_status(principal_id, event_detail):
    """Determine whether a key was CDK-provisioned or manually created.

    Retries once after 2 seconds if tags are not yet available (race condition).
    """
    import time

    for attempt in range(2):
        try:
            response = iam_client.list_user_tags(UserName=principal_id)
            tags = {t['Key']: t['Value'] for t in response.get('Tags', [])}

            provisioned_tag = tags.get('BedrockBudgeteer:Provisioned')
            if provisioned_tag == 'cdk':
                return {
                    'provisioned_by': 'cdk',
                    'team': tags.get('BedrockBudgeteer:Team', 'unknown'),
                    'purpose': tags.get('BedrockBudgeteer:Purpose', 'unknown'),
                    'budget_tier': tags.get('BedrockBudgeteer:BudgetTier', 'standard'),
                }

            if provisioned_tag is not None:
                # Has a Provisioned tag but value is not 'cdk' — treat as manual
                break

            # No Provisioned tag found — retry once in case of race condition
            if attempt == 0:
                logger.info(f"No Provisioned tag found for {principal_id}, retrying in 2s")
                time.sleep(2)
                continue

        except Exception as e:
            logger.warning(f"Error listing tags for {principal_id} (attempt {attempt + 1}): {e}")
            if attempt == 0:
                time.sleep(2)
                continue
            break

    # Not CDK-provisioned — auto-tag as rogue
    _auto_tag_rogue_key(principal_id, event_detail=event_detail)
    return {
        'provisioned_by': 'manual',
        'team': 'unassigned',
        'purpose': 'unassigned',
        'budget_tier': 'low',
    }


def _auto_tag_rogue_key(principal_id, event_detail=None):
    """Apply default tags to an unprovisioned key and alert."""
    if event_detail is None:
        event_detail = {}

    default_tags = [
        {'Key': 'BedrockBudgeteer:Team', 'Value': 'unassigned'},
        {'Key': 'BedrockBudgeteer:Purpose', 'Value': 'unassigned'},
        {'Key': 'BedrockBudgeteer:BudgetTier', 'Value': 'low'},
        {'Key': 'BedrockBudgeteer:Provisioned', 'Value': 'manual'},
        {'Key': 'BedrockBudgeteer:ManagedBy', 'Value': 'bedrock-budgeteer'},
        {'Key': 'CostAllocation:Team', 'Value': 'unassigned'},
        {'Key': 'CostAllocation:Purpose', 'Value': 'unassigned'},
    ]

    try:
        iam_client.tag_user(UserName=principal_id, Tags=default_tags)
        logger.info(f"Applied default tags to rogue key: {principal_id}")
    except Exception as e:
        logger.error(f"Failed to tag rogue key {principal_id}: {e}")

    # Publish SNS alert
    user_identity = event_detail.get('userIdentity', {})
    topic_arn = os.environ.get('BUDGET_ALERTS_SNS_TOPIC_ARN', '')
    if topic_arn:
        try:
            message = {
                'alert': 'RogueKeyDetected',
                'principal_id': principal_id,
                'created_by': user_identity.get('arn', 'unknown'),
                'event_time': event_detail.get('eventTime', 'unknown'),
                'source_ip': event_detail.get('sourceIPAddress', 'unknown'),
            }
            sns_client.publish(
                TopicArn=topic_arn,
                Subject=f"Rogue Bedrock API Key Detected: {principal_id}",
                Message=json.dumps(message, default=str),
            )
            logger.info(f"Published rogue key alert for {principal_id}")
        except Exception as e:
            logger.error(f"Failed to publish SNS alert for rogue key {principal_id}: {e}")

    # Publish CloudWatch metric
    MetricsPublisher.publish_budget_metric(
        'RogueKeyDetected',
        1.0,
        'Count',
        {'Environment': os.environ.get('ENVIRONMENT', 'unknown')}
    )


def _ensure_global_api_key_pool(table):
    """Create the GLOBAL_API_KEY_POOL row if it does not already exist."""
    now = datetime.now(timezone.utc)

    global_budget = ConfigurationManager.get_parameter(
        '/bedrock-budgeteer/global/api_key_pool_budget_usd', 500
    )
    refresh_days = int(ConfigurationManager.get_parameter(
        '/bedrock-budgeteer/global/budget_refresh_period_days', 30
    ))

    try:
        table.put_item(
            Item={
                'principal_id': 'GLOBAL_API_KEY_POOL',
                'account_type': 'api_key_pool',
                'budget_limit_usd': Decimal(str(global_budget)),
                'spent_usd': Decimal('0'),
                'status': 'active',
                'threshold_state': 'normal',
                'refresh_period_days': refresh_days,
                'budget_refresh_date': (now + timedelta(days=refresh_days)).isoformat(),
                'created_epoch': int(now.timestamp()),
                'last_updated_epoch': int(now.timestamp()),
            },
            ConditionExpression='attribute_not_exists(principal_id)'
        )
        logger.info("Created GLOBAL_API_KEY_POOL row")
    except Exception as e:
        # ConditionalCheckFailedException means it already exists — safe to ignore
        if 'ConditionalCheckFailedException' in str(e):
            pass
        else:
            logger.error(f"Error creating GLOBAL_API_KEY_POOL: {e}")


def _register_key_budget(principal_id, provisioning_info, table):
    """Create a budget record for a Bedrock API key."""
    now = datetime.now(timezone.utc)
    provisioned_by = provisioning_info.get('provisioned_by', 'manual')
    team = provisioning_info.get('team', 'unassigned')
    purpose = provisioning_info.get('purpose', 'unassigned')
    budget_tier = provisioning_info.get('budget_tier', 'low')

    if provisioned_by == 'cdk':
        tier_budget = ConfigurationManager.get_parameter(
            f'/bedrock-budgeteer/global/budget_tier_{budget_tier}_usd', 50
        )
        has_carveout = True
        budget_limit_usd = Decimal(str(tier_budget))
    else:
        has_carveout = False
        budget_limit_usd = None

    refresh_days = int(ConfigurationManager.get_parameter(
        '/bedrock-budgeteer/global/budget_refresh_period_days', 30
    ))

    budget_item = {
        'principal_id': principal_id,
        'account_type': 'bedrock_api_key',
        'spent_usd': Decimal('0'),
        'status': 'active',
        'threshold_state': 'normal',
        'has_carveout': has_carveout,
        'team': team,
        'purpose': purpose,
        'budget_tier': budget_tier,
        'provisioned_by': provisioned_by,
        'budget_period_start': now.isoformat(),
        'budget_refresh_date': (now + timedelta(days=refresh_days)).isoformat(),
        'created_epoch': int(now.timestamp()),
        'last_updated_epoch': int(now.timestamp()),
    }

    if budget_limit_usd is not None:
        budget_item['budget_limit_usd'] = budget_limit_usd

    table.put_item(Item=budget_item)
    logger.info(f"Registered budget for {principal_id}: carveout={has_carveout}, tier={budget_tier}")

    MetricsPublisher.publish_budget_metric(
        'BudgetInitialized',
        1.0,
        'Count',
        {'AccountType': 'bedrock_api_key', 'Environment': os.environ.get('ENVIRONMENT', 'unknown')}
    )

    EventPublisher.publish_budget_event(
        'Budget Initialized',
        {
            'principal_id': principal_id,
            'account_type': 'bedrock_api_key',
            'has_carveout': has_carveout,
            'budget_tier': budget_tier,
            'provisioned_by': provisioned_by,
            'budget_limit_usd': float(budget_limit_usd) if budget_limit_usd is not None else None,
        }
    )


def _handle_tag_change(principal_id, event_detail, table):
    """Re-check tags after a TagUser/UntagUser event and reconcile."""
    try:
        response = iam_client.list_user_tags(UserName=principal_id)
        tags = {t['Key']: t['Value'] for t in response.get('Tags', [])}
    except Exception as e:
        logger.error(f"Failed to list tags for {principal_id} during tag change: {e}")
        return

    # If the Provisioned tag was removed, re-apply it from DynamoDB record and alert
    provisioned_value = tags.get('BedrockBudgeteer:Provisioned')
    if provisioned_value is None:
        # Look up the original provisioned_by from DynamoDB to restore correctly
        try:
            item_resp = table.get_item(Key={'principal_id': principal_id}, ProjectionExpression='provisioned_by')
            original_provisioned = item_resp.get('Item', {}).get('provisioned_by', 'manual')
        except Exception:
            original_provisioned = 'manual'
        logger.warning(f"Provisioned tag removed from {principal_id} — re-applying as '{original_provisioned}'")
        try:
            iam_client.tag_user(
                UserName=principal_id,
                Tags=[{'Key': 'BedrockBudgeteer:Provisioned', 'Value': original_provisioned}]
            )
        except Exception as e:
            logger.error(f"Failed to re-apply Provisioned tag to {principal_id}: {e}")

        topic_arn = os.environ.get('BUDGET_ALERTS_SNS_TOPIC_ARN', '')
        if topic_arn:
            try:
                sns_client.publish(
                    TopicArn=topic_arn,
                    Subject=f"Tag Tampering Detected: {principal_id}",
                    Message=json.dumps({
                        'alert': 'TagTamperingDetected',
                        'principal_id': principal_id,
                        'missing_tag': 'BedrockBudgeteer:Provisioned',
                        'event_time': event_detail.get('eventTime', 'unknown'),
                    }, default=str),
                )
            except Exception as e:
                logger.error(f"Failed to publish tag tampering alert: {e}")

    # Update DynamoDB record with current tag values
    update_fields = {}
    if 'BedrockBudgeteer:Team' in tags:
        update_fields['team'] = tags['BedrockBudgeteer:Team']
    if 'BedrockBudgeteer:Purpose' in tags:
        update_fields['purpose'] = tags['BedrockBudgeteer:Purpose']
    if 'BedrockBudgeteer:BudgetTier' in tags:
        update_fields['budget_tier'] = tags['BedrockBudgeteer:BudgetTier']

    if update_fields:
        update_fields['last_updated_epoch'] = int(datetime.now(timezone.utc).timestamp())
        update_parts = []
        expr_values = {}
        for key, value in update_fields.items():
            safe_key = key.replace('-', '_')
            update_parts.append(f'{key} = :{safe_key}')
            expr_values[f':{safe_key}'] = value if not isinstance(value, float) else Decimal(str(value))

        try:
            table.update_item(
                Key={'principal_id': principal_id},
                UpdateExpression='SET ' + ', '.join(update_parts),
                ExpressionAttributeValues=expr_values,
            )
            logger.info(f"Updated budget record tags for {principal_id}: {update_fields}")
        except Exception as e:
            logger.error(f"Failed to update budget record for {principal_id}: {e}")
'''
