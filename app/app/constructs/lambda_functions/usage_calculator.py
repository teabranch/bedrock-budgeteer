"""
Usage Calculator Lambda Function
Process Bedrock invocation logs from Kinesis Data Firehose and calculate token-based costs
"""



def get_usage_calculator_function_code() -> str:
    """Get the Lambda function code for usage calculator"""
    return '''
import base64
import gzip

def lambda_handler(event, context):
    """
    Process Bedrock invocation logs from Kinesis Data Firehose
    Calculate token-based costs and update user budgets
    """
    logger.info(f"=== USAGE CALCULATOR LAMBDA STARTED ===")
    logger.info(f"Event type: {type(event)}")
    logger.info(f"Event keys: {list(event.keys()) if isinstance(event, dict) else 'Not a dict'}")
    logger.info(f"Processing usage calculation event with {len(event.get('records', []))} records")
    
    # Log the raw event structure (truncated for large events)
    event_str = str(event)
    if len(event_str) > 1000:
        logger.info(f"Event (first 1000 chars): {event_str[:1000]}...")
    else:
        logger.info(f"Full event: {event}")
    
    processed_records = []
    
    try:
        for i, record in enumerate(event.get('records', [])):
            # Decode Firehose record
            try:
                logger.info(f"=== PROCESSING RECORD {i+1}/{len(event.get('records', []))} ===")
                logger.info(f"Record ID: {record.get('recordId', 'UNKNOWN')}")
                logger.info(f"Record keys: {list(record.keys())}")
                
                # Firehose base64 encodes data
                encoded_data = record['data']
                logger.info(f"Encoded data length: {len(encoded_data)} characters")
                
                decoded_data = base64.b64decode(encoded_data)
                logger.info(f"Decoded data length: {len(decoded_data)} bytes")
                
                # Check if data is gzipped
                original_data = decoded_data
                try:
                    decoded_data = gzip.decompress(decoded_data)
                    logger.info(f"Data was gzipped, uncompressed to {len(decoded_data)} bytes")
                except:
                    logger.info("Data was not gzipped")
                    pass  # Not gzipped
                
                log_data_str = decoded_data.decode('utf-8')
                logger.info(f"Log data string length: {len(log_data_str)} characters")
                
                # Log first 500 chars of the actual log data
                if len(log_data_str) > 500:
                    logger.info(f"Log data preview: {log_data_str[:500]}...")
                else:
                    logger.info(f"Full log data: {log_data_str}")
                
                log_data = json.loads(log_data_str)
                logger.info(f"Parsed log data keys: {list(log_data.keys())}")
                
                # Process Bedrock invocation log
                logger.info(f"Calling process_bedrock_log for record {i+1}")
                result = process_bedrock_log(log_data)
                logger.info(f"process_bedrock_log returned: {result}")
                
                processed_records.append({
                    'recordId': record['recordId'],
                    'result': 'Ok' if result else 'ProcessingFailed'
                })
                
            except Exception as e:
                logger.error(f"Error processing record {record.get('recordId')}: {e}", exc_info=True)
                logger.error(f"Record data that caused error: {record}")
                processed_records.append({
                    'recordId': record['recordId'],
                    'result': 'ProcessingFailed'
                })
        
        logger.info(f"=== USAGE CALCULATOR LAMBDA COMPLETED ===")
        logger.info(f"Processed {len(processed_records)} records")
        logger.info(f"Results: {[r['result'] for r in processed_records]}")
        return {'records': processed_records}
        
    except Exception as e:
        logger.error(f"Error in usage calculator: {e}", exc_info=True)
        
        # Mark all records as failed
        failed_results = {
            'records': [
                {'recordId': record['recordId'], 'result': 'ProcessingFailed'}
                for record in event.get('records', [])
            ]
        }
        logger.error(f"=== USAGE CALCULATOR LAMBDA FAILED ===")
        logger.error(f"Returning {len(failed_results['records'])} failed records")
        return failed_results

def process_bedrock_invocation_log(log_data):
    """Process CloudWatch Bedrock invocation log (direct from Bedrock service)"""
    try:
        logger.info("=== PROCESSING BEDROCK INVOCATION LOG ===")
        logger.info(f"Log data type: {type(log_data)}")
        logger.info(f"Log data keys: {list(log_data.keys())}")
        
        # Extract token usage from CloudWatch invocation log format
        input_data = log_data.get('input', {})
        output_data = log_data.get('output', {})
        
        logger.info(f"Input data keys: {list(input_data.keys())}")
        logger.info(f"Output data keys: {list(output_data.keys())}")
        
        # Get output tokens from the message usage first (most reliable)
        output_tokens = 0
        input_tokens = 0
        cache_creation_tokens = 0
        cache_read_tokens = 0
        
        output_body = output_data.get('outputBodyJson', [])
        logger.info(f"Output body length: {len(output_body) if output_body else 0}")
        
        if output_body:
            logger.info(f"Output body first item keys: {list(output_body[0].keys()) if output_body else []}")
            for i, item in enumerate(output_body):
                logger.info(f"Output item {i}: type={item.get('type')}")
                if item.get('type') == 'message_start':
                    message = item.get('message', {})
                    usage = message.get('usage', {})
                    
                    # Extract all token counts from usage
                    input_tokens = usage.get('input_tokens', 0)
                    cache_creation_tokens = usage.get('cache_creation_input_tokens', 0)
                    cache_read_tokens = usage.get('cache_read_input_tokens', 0)
                    output_tokens = usage.get('output_tokens', 0)
                    
                    logger.info(f"Token usage from message: input={input_tokens}, cache_creation={cache_creation_tokens}, cache_read={cache_read_tokens}, output={output_tokens}")
                    break
        
        # If no tokens found in message usage, fall back to top-level fields
        if input_tokens == 0 and cache_read_tokens == 0 and cache_creation_tokens == 0 and output_tokens == 0:
            logger.info("No tokens found in message usage, checking top-level fields")
            input_tokens = input_data.get('inputTokenCount', 0)
            cache_read_tokens = input_data.get('cacheReadInputTokenCount', 0) 
            cache_creation_tokens = input_data.get('cacheWriteInputTokenCount', 0)  # Note: This maps to creation tokens
            output_tokens = output_data.get('outputTokenCount', 0)
            logger.info(f"Top-level token counts - Input: {input_tokens}, Cache Read: {cache_read_tokens}, Cache Write: {cache_creation_tokens}, Output: {output_tokens}")
        
        # Total input tokens include all input processing
        total_input_tokens = input_tokens + cache_read_tokens + cache_creation_tokens
        logger.info(f"Final token counts - Total Input: {total_input_tokens} (input={input_tokens} + cache_read={cache_read_tokens} + cache_creation={cache_creation_tokens}), Output: {output_tokens}")
        
        if total_input_tokens == 0 and output_tokens == 0:
            logger.warning("No token usage found in invocation log")
            return True
        
        # Extract model information - check top level first, then output message
        model_id = log_data.get('modelId', '')
        logger.info(f"Model ID from top level: {model_id}")
        
        if not model_id and output_body:
            # Try to extract from output message
            for item in output_body:
                if item.get('type') == 'message_start':
                    message = item.get('message', {})
                    model_id = message.get('model', '')
                    logger.info(f"Extracted model_id from output message: {model_id}")
                    break
        
        if not model_id:
            logger.warning("No model ID found in invocation log")
            logger.warning(f"Top-level keys: {list(log_data.keys())}")
            logger.warning(f"Output body structure: {output_body[:1] if output_body else 'None'}")
            return True
        
        # Extract principal ID from log metadata (added by logs forwarder) or from identity ARN
        metadata = log_data.get('_metadata', {})
        principal_id = metadata.get('principal_id')
        logger.info(f"Metadata: {metadata}")
        logger.info(f"Principal ID from metadata: {principal_id}")
        
        # If no principal_id in metadata, try to extract from identity ARN
        if not principal_id:
            identity = log_data.get('identity', {})
            identity_arn = identity.get('arn', '')
            logger.info(f"Identity ARN: {identity_arn}")
            
            if identity_arn and ':user/' in identity_arn:
                principal_id = identity_arn.split(':user/')[-1]
                logger.info(f"Extracted principal_id from identity ARN: {principal_id}")
        
        if not principal_id:
            logger.warning("Could not extract principal ID from invocation log metadata or identity")
            logger.warning(f"Available log data keys: {list(log_data.keys())}")
            logger.warning(f"_metadata content: {metadata}")
            logger.warning(f"identity content: {log_data.get('identity', {})}")
            return True
        
        # Calculate cost with cache token awareness
        region = log_data.get('region', log_data.get('awsRegion', 'us-east-1'))  # Extract from log or default
        logger.info(f"Calculating cost for model={model_id}, input_tokens={input_tokens}, output_tokens={output_tokens}, cache_creation={cache_creation_tokens}, cache_read={cache_read_tokens}, region={region}")
        cost = BedrockPricingCalculator.calculate_cost_with_cache(model_id, input_tokens, output_tokens, cache_creation_tokens, cache_read_tokens, region)
        logger.info(f"Calculated cost: ${cost:.6f}")
        
        # Record usage tracking
        logger.info(f"Recording usage tracking for {principal_id}")
        record_usage_tracking(principal_id, model_id, cost, total_input_tokens, output_tokens, 'bedrock_invocation')
        
        # Update user budget
        logger.info(f"Updating budget for {principal_id} with cost ${cost:.6f} from model {model_id}")
        update_user_budget(principal_id, model_id, cost, total_input_tokens, output_tokens)
        
        # Publish audit event for usage cost calculation
        logger.info(f"Publishing audit event for usage calculation")
        EventPublisher.publish_budget_event(
            'Usage Cost Calculated',
            {
                'principal_id': principal_id,
                'model_id': model_id,
                'cost_usd': float(cost),
                'input_tokens': total_input_tokens,
                'output_tokens': output_tokens,
                'total_tokens': total_input_tokens + output_tokens,
                'usage_type': 'bedrock_invocation',
                'region': region
            }
        )
        
        # Publish metrics
        MetricsPublisher.publish_budget_metric(
            'TokensProcessed',
            total_input_tokens + output_tokens,
            'Count',
            {'ModelId': model_id, 'PrincipalId': principal_id}
        )
        
        MetricsPublisher.publish_budget_metric(
            'CostCalculated',
            cost,
            'None',
            {'ModelId': model_id, 'PrincipalId': principal_id}
        )
        
        logger.info(f"Processed invocation log for {principal_id}: {total_input_tokens} input + {output_tokens} output tokens, cost: ${cost:.6f}")
        return True
        
    except Exception as e:
        logger.error(f"Error processing Bedrock invocation log: {e}")
        return False

def process_bedrock_log(log_data):
    """Process individual Bedrock log (handles both CloudTrail API logs and CloudWatch invocation logs)"""
    try:
        logger.info("=== PROCESS_BEDROCK_LOG ENTRY ===")
        logger.info(f"Log data keys: {list(log_data.keys())}")
        
        # Check if this is a CloudWatch invocation log (direct from Bedrock service)
        actual_log_data = log_data
        
        # Handle wrapped log format where the actual Bedrock log is JSON-encoded in a 'message' field
        if 'message' in log_data and isinstance(log_data['message'], str):
            logger.info("Found message field - attempting to parse as nested Bedrock log")
            try:
                # Parse the message field as JSON to get the actual Bedrock log
                actual_log_data = json.loads(log_data['message'])
                logger.info(f"Successfully parsed message field. Actual log keys: {list(actual_log_data.keys())}")
                
                # Copy over metadata from the wrapper if it exists
                if '_metadata' in log_data:
                    actual_log_data['_metadata'] = log_data['_metadata']
                    logger.info("Copied metadata from wrapper to actual log data")
                    
            except json.JSONDecodeError as e:
                logger.warning(f"Failed to parse message field as JSON: {e}")
                logger.warning(f"Message content preview: {log_data['message'][:200]}...")
                # Continue with original log_data
                actual_log_data = log_data
        
        # Now check if this is a CloudWatch invocation log (direct from Bedrock service)
        if 'input' in actual_log_data and 'output' in actual_log_data:
            logger.info("Detected CloudWatch invocation log format - routing to process_bedrock_invocation_log")
            return process_bedrock_invocation_log(actual_log_data)
        
        logger.info("Detected CloudTrail API log format - processing as CloudTrail log")
        
        # Handle CloudTrail API logs (legacy format)
        event_name = actual_log_data.get('eventName')
        if event_name not in ['InvokeModel', 'InvokeModelWithResponseStream']:
            return True  # Skip non-invocation events
        
        user_identity = actual_log_data.get('userIdentity', {})
        request_params = actual_log_data.get('requestParameters', {})
        response_elements = actual_log_data.get('responseElements', {})
        
        # Extract principal ID
        principal_id = None
        if user_identity.get('type') == 'IAMUser':
            principal_id = user_identity.get('userName')
        elif user_identity.get('type') == 'AssumedRole':
            session_context = user_identity.get('sessionContext', {})
            session_issuer = session_context.get('sessionIssuer', {}) if session_context else {}
            principal_id = session_issuer.get('userName') if session_issuer else None
        
        if not principal_id:
            logger.warning("Could not extract principal ID from log")
            return True
        
        # Extract model information
        model_id = request_params.get('modelId', '')
        if not model_id:
            logger.warning("No model ID found in request")
            return True
        
        # Extract token usage (CloudTrail format)
        input_tokens = response_elements.get('usage', {}).get('inputTokens', 0)
        output_tokens = response_elements.get('usage', {}).get('outputTokens', 0)
        
        if input_tokens == 0 and output_tokens == 0:
            logger.warning("No token usage found in response")
            return True
        
        # Calculate cost
        region = actual_log_data.get('awsRegion', 'us-east-1')
        cost = BedrockPricingCalculator.calculate_cost(model_id, input_tokens, output_tokens, region)
        
        # Record usage tracking
        logger.info(f"Recording usage tracking for {principal_id} (CloudTrail)")
        record_usage_tracking(principal_id, model_id, cost, input_tokens, output_tokens, 'cloudtrail_api')
        
        # Update user budget
        update_user_budget(principal_id, model_id, cost, input_tokens, output_tokens)
        
        # Publish audit event for usage cost calculation
        logger.info(f"Publishing audit event for CloudTrail usage calculation")
        EventPublisher.publish_budget_event(
            'Usage Cost Calculated',
            {
                'principal_id': principal_id,
                'model_id': model_id,
                'cost_usd': float(cost),
                'input_tokens': input_tokens,
                'output_tokens': output_tokens,
                'total_tokens': input_tokens + output_tokens,
                'usage_type': 'cloudtrail_api',
                'region': region
            }
        )
        
        # Publish metrics
        MetricsPublisher.publish_budget_metric(
            'TokensProcessed',
            input_tokens + output_tokens,
            'Count',
            {'ModelId': model_id, 'PrincipalId': principal_id}
        )
        
        MetricsPublisher.publish_budget_metric(
            'CostCalculated',
            cost,
            'None',
            {'ModelId': model_id, 'PrincipalId': principal_id}
        )
        
        return True
        
    except Exception as e:
        logger.error(f"Error processing Bedrock log: {e}")
        return False

def record_usage_tracking(principal_id, model_id, cost, input_tokens, output_tokens, usage_type):
    """Record usage data in the usage tracking table"""
    try:
        usage_tracking_table = dynamodb.Table(os.environ['USAGE_TRACKING_TABLE'])
        current_time = datetime.now(timezone.utc)
        
        # Create usage record
        usage_record = {
            'principal_id': principal_id,
            'timestamp': current_time.isoformat(),
            'service': 'bedrock',
            'model_id': model_id,
            'usage_type': usage_type,
            'input_tokens': input_tokens,
            'output_tokens': output_tokens,
            'total_tokens': input_tokens + output_tokens,
            'cost_usd': Decimal(str(cost)),
            'region': 'us-east-1',
            'created_epoch': int(current_time.timestamp())
        }
        
        usage_tracking_table.put_item(Item=usage_record)
        logger.info(f"Successfully recorded usage tracking for {principal_id}: {input_tokens}+{output_tokens} tokens, ${cost:.6f}")
        
    except Exception as e:
        logger.error(f"Error recording usage tracking for {principal_id}: {e}")
        # Don't raise - usage tracking failure shouldn't stop budget updates

def update_user_budget(principal_id, model_id, cost, input_tokens, output_tokens):
    """Update user budget with new spending"""
    try:
        user_budgets_table = dynamodb.Table(os.environ['USER_BUDGETS_TABLE'])
        current_time = datetime.now(timezone.utc)
        
        logger.info(f"Attempting to update budget for {principal_id}: cost=${cost:.6f}, model={model_id}, tokens={input_tokens}+{output_tokens}")
        
        # Use atomic update to handle concurrent access
        # Handle case where budget record might not exist yet
        try:
            response = user_budgets_table.update_item(
                Key={'principal_id': principal_id},
                UpdateExpression="SET spent_usd = if_not_exists(spent_usd, :zero) + :cost, last_updated_epoch = :timestamp, model_spend_breakdown.#model_id = if_not_exists(model_spend_breakdown.#model_id, :zero) + :cost",
                ExpressionAttributeNames={
                    '#model_id': model_id
                },
                ExpressionAttributeValues={
                    ':cost': Decimal(str(cost)),
                    ':timestamp': int(current_time.timestamp()),
                    ':zero': Decimal('0.0')
                },
                ReturnValues='ALL_NEW'
            )
            logger.info(f"Successfully updated budget for {principal_id}: spent_usd now ${response['Attributes']['spent_usd']}")
        except Exception as update_error:
            logger.error(f"Failed to update existing budget record for {principal_id}: {update_error}")
            # If update fails (e.g., item doesn't exist), try to create a basic budget record first
            try:
                logger.info(f"Creating missing budget record for {principal_id}")
                create_basic_budget_record(principal_id, cost, model_id, current_time)
                return  # Budget record created successfully with the cost included
            except Exception as create_error:
                logger.error(f"Failed to create budget record for {principal_id}: {create_error}")
                raise update_error  # Re-raise original error
        
        # Check if budget threshold exceeded
        updated_item = response['Attributes']
        spent_usd = float(updated_item['spent_usd'])
        budget_limit_usd = float(updated_item['budget_limit_usd'])
        
        thresholds = ConfigurationManager.get_budget_thresholds()
        warn_threshold = budget_limit_usd * (thresholds['warn_percent'] / 100)
        critical_threshold = budget_limit_usd * (thresholds['critical_percent'] / 100)
        
        current_threshold_state = updated_item.get('threshold_state', 'normal')
        new_threshold_state = current_threshold_state
        
        if spent_usd >= critical_threshold:
            new_threshold_state = 'critical'
        elif spent_usd >= warn_threshold:
            new_threshold_state = 'warning'
        else:
            new_threshold_state = 'normal'
        
        # Update threshold state if changed
        if new_threshold_state != current_threshold_state:
            user_budgets_table.update_item(
                Key={'principal_id': principal_id},
                UpdateExpression='SET threshold_state = :state',
                ExpressionAttributeValues={':state': new_threshold_state}
            )
            
            # Publish threshold event
            EventPublisher.publish_budget_event(
                'Budget Threshold Changed',
                {
                    'principal_id': principal_id,
                    'previous_state': current_threshold_state,
                    'new_state': new_threshold_state,
                    'spent_usd': spent_usd,
                    'budget_limit_usd': budget_limit_usd,
                    'percent_used': (spent_usd / budget_limit_usd) * 100
                }
            )
        
    except Exception as e:
        logger.error(f"Error updating user budget for {principal_id}: {e}")
        raise

def create_basic_budget_record(principal_id, initial_cost, model_id, current_time):
    """Create a basic budget record when one doesn't exist"""
    try:
        user_budgets_table = dynamodb.Table(os.environ['USER_BUDGETS_TABLE'])
        
        # Get default budget limit for Bedrock API key
        default_budget = ConfigurationManager.get_parameter(
            '/bedrock-budgeteer/global/default_user_budget_usd', 5.0
        )
        
        # Get budget refresh period
        refresh_period_days = ConfigurationManager.get_parameter(
            '/bedrock-budgeteer/production/cost/budget_refresh_period_days', 30
        )
        
        # Calculate next refresh date
        refresh_date = current_time + timedelta(days=int(refresh_period_days))
        
        # Create basic budget record with initial cost
        budget_item = {
            'principal_id': principal_id,
            'account_type': 'bedrock_api_key',  # Default for usage-first discovery
            'budget_limit_usd': Decimal(str(default_budget)),
            'spent_usd': Decimal(str(initial_cost)),  # Start with the current cost
            'status': 'active',
            'threshold_state': 'normal',
            'time_window_start': current_time.isoformat(),
            'last_updated_epoch': int(current_time.timestamp()),
            'model_spend_breakdown': {model_id: Decimal(str(initial_cost))},
            'anomaly_score': Decimal('0.0'),
            'created_epoch': int(current_time.timestamp()),
            'grace_deadline_epoch': None,
            'budget_period_start': current_time.isoformat(),
            'budget_refresh_date': refresh_date.isoformat(),
            'refresh_period_days': int(refresh_period_days),
            'refresh_count': 0,
            'auto_created': True  # Flag to indicate this was auto-created from usage
        }
        
        user_budgets_table.put_item(
            Item=budget_item,
            ConditionExpression='attribute_not_exists(principal_id)'  # Only create if doesn't exist
        )
        
        logger.info(f"Created basic budget record for {principal_id} with initial cost ${initial_cost:.6f}")
        
        # Publish audit event for auto-created budget
        EventPublisher.publish_budget_event(
            'Budget Auto-Created',
            {
                'principal_id': principal_id,
                'account_type': 'bedrock_api_key',
                'budget_limit_usd': float(default_budget),
                'initial_cost': float(initial_cost),
                'model_id': model_id,
                'reason': 'usage_detected_without_existing_budget'
            }
        )
        
    except Exception as e:
        logger.error(f"Error creating basic budget record for {principal_id}: {e}")
        raise
'''
