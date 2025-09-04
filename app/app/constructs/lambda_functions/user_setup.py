"""
User Setup Lambda Function
Process CloudTrail IAM events to initialize Bedrock API key budgets
"""



def get_user_setup_function_code() -> str:
    """Get the Lambda function code for user setup"""
    return '''
def lambda_handler(event, context):
    """
    Process CloudTrail IAM events to initialize Bedrock API key budgets
    
    ONLY monitors Bedrock API keys created via Bedrock console:
    - CreateUser events with BedrockAPIKey- prefix userName  
    - CreateServiceSpecificCredential for existing Bedrock API key users
    - AttachUserPolicy for existing Bedrock API key users
    
    IGNORES all other IAM users, service accounts, and regular user events
    """
    logger.info(f"Processing user setup event: {json.dumps(event)}")
    
    try:
        # Parse EventBridge event
        if 'detail' not in event:
            logger.error("Invalid event format - missing detail")
            return {'statusCode': 400, 'body': 'Invalid event format'}
        
        detail = event.get('detail', {})
        event_name = detail.get('eventName')
        user_identity = detail.get('userIdentity', {})
        response_elements = detail.get('responseElements', {})
        
        # ONLY process Bedrock API key events - ignore all other IAM activities
        principal_id = None
        account_type = 'bedrock_api_key'  # Only support bedrock_api_key type
        is_bedrock_api_key = False
        
        # Check for Bedrock API key creation via CreateUser event
        if event_name == 'CreateUser' and response_elements:
            user_info = response_elements.get('user', {})
            created_user_name = user_info.get('userName', '')
            
            if created_user_name.startswith('BedrockAPIKey-'):
                principal_id = created_user_name
                is_bedrock_api_key = True
                logger.info(f"Detected Bedrock API key creation: {principal_id}")
            else:
                # Ignore regular user creation - not our concern
                logger.info(f"Ignoring regular user creation: {created_user_name} (not a Bedrock API key)")
                return {'statusCode': 200, 'body': 'Event ignored - not a Bedrock API key'}
        
        # Check for service-specific credential creation (only for Bedrock API keys)
        elif event_name == 'CreateServiceSpecificCredential':
            request_parameters = detail.get('requestParameters', {})
            target_user_name = request_parameters.get('userName', '')
            
            if target_user_name.startswith('BedrockAPIKey-'):
                principal_id = target_user_name
                is_bedrock_api_key = True
                logger.info(f"Bedrock API service credential created for: {principal_id}")
            else:
                # Ignore service credential creation for non-Bedrock users
                logger.info(f"Ignoring service credential creation for: {target_user_name} (not a Bedrock API key)")
                return {'statusCode': 200, 'body': 'Event ignored - not a Bedrock API key'}
        
        # Check for policy events on existing Bedrock API key users
        elif event_name in ['AttachUserPolicy', 'CreateAccessKey', 'PutUserPolicy']:
            # Extract the target user from various event types
            request_parameters = detail.get('requestParameters', {})
            target_user = request_parameters.get('userName') or user_identity.get('userName', '')
            
            if target_user and target_user.startswith('BedrockAPIKey-'):
                principal_id = target_user
                is_bedrock_api_key = True
                logger.info(f"Event {event_name} detected for existing Bedrock API key user: {principal_id}")
            else:
                # Ignore policy events for non-Bedrock users
                logger.info(f"Ignoring {event_name} for: {target_user} (not a Bedrock API key)")
                return {'statusCode': 200, 'body': 'Event ignored - not a Bedrock API key'}
        
        else:
            # Ignore all other event types (role events, other IAM events, etc.)
            logger.info(f"Ignoring event type: {event_name} (not relevant to Bedrock API keys)")
            return {'statusCode': 200, 'body': 'Event ignored - not relevant to Bedrock API keys'}
        
        if not principal_id or not is_bedrock_api_key:
            logger.warning("No Bedrock API key detected in event")
            return {'statusCode': 200, 'body': 'No Bedrock API key detected'}
        
        # Get or create budget entry
        user_budgets_table = dynamodb.Table(os.environ['USER_BUDGETS_TABLE'])
        
        # Check if budget already exists (idempotency)
        try:
            response = user_budgets_table.get_item(Key={'principal_id': principal_id})
            if 'Item' in response:
                logger.info(f"Budget already exists for {principal_id}")
                return {'statusCode': 200, 'body': 'Budget already exists'}
        except Exception as e:
            logger.error(f"Error checking existing budget: {e}")
        
        # Get default budget limit for Bedrock API key (only type we support)
        default_budget = ConfigurationManager.get_parameter(
            '/bedrock-budgeteer/global/default_user_budget_usd', 5.0
        )
        
        # Get budget refresh period
        refresh_period_days = ConfigurationManager.get_parameter(
            '/bedrock-budgeteer/production/cost/budget_refresh_period_days', 30
        )
        
        # Create new budget entry
        current_time = datetime.now(timezone.utc)
        
        # Calculate next refresh date
        refresh_date = current_time + timedelta(days=int(refresh_period_days))
        budget_item = {
            'principal_id': principal_id,
            'account_type': account_type,
            'budget_limit_usd': Decimal(str(default_budget)),
            'spent_usd': Decimal('0.0'),
            'status': 'active',
            'threshold_state': 'normal',
            'time_window_start': current_time.isoformat(),
            'last_updated_epoch': int(current_time.timestamp()),
            'model_spend_breakdown': {},
            'anomaly_score': Decimal('0.0'),
            'created_epoch': int(current_time.timestamp()),
            'grace_deadline_epoch': None,
            'budget_period_start': current_time.isoformat(),
            'budget_refresh_date': refresh_date.isoformat(),
            'refresh_period_days': int(refresh_period_days),
            'refresh_count': 0
        }
        
        user_budgets_table.put_item(Item=budget_item)
        
        # Publish audit event with enhanced Bedrock API key information
        audit_data = {
            'principal_id': principal_id,
            'account_type': account_type,
            'budget_limit_usd': float(default_budget),
            'event_name': event_name,
            'is_bedrock_api_key': is_bedrock_api_key,
            'source_event': detail
        }
        
        # Add additional context for Bedrock API key events
        if is_bedrock_api_key:
            audit_data['bedrock_api_key_detected'] = True
            if event_name == 'CreateUser' and response_elements:
                user_info = response_elements.get('user', {})
                audit_data['user_arn'] = user_info.get('arn', '')
                audit_data['user_id'] = user_info.get('userId', '')
                audit_data['create_date'] = user_info.get('createDate', '')
        
        EventPublisher.publish_budget_event(
            'Budget Initialized',
            audit_data
        )
        
        # Publish metric
        MetricsPublisher.publish_budget_metric(
            'BudgetInitialized',
            1.0,
            'Count',
            {'AccountType': account_type, 'Environment': os.environ['ENVIRONMENT']}
        )
        
        logger.info(f"Successfully initialized budget for {principal_id}")
        return {'statusCode': 200, 'body': 'Budget initialized successfully'}
        
    except Exception as e:
        logger.error(f"Error processing user setup event: {e}", exc_info=True)
        
        # Publish error metric
        MetricsPublisher.publish_budget_metric(
            'UserSetupErrors',
            1.0,
            'Count',
            {'Environment': os.environ['ENVIRONMENT']}
        )
        
        raise  # Re-raise to trigger DLQ
'''
