"""
Usage Calculator Lambda Function
Process Bedrock invocation logs from Kinesis Data Firehose and calculate token-based costs.
Supports: InvokeModel, InvokeModelWithResponseStream, Converse, ConverseStream,
          Agents, Flows, Knowledge Bases, image/video models, and batch inference.
"""



def get_usage_calculator_function_code() -> str:
    """Get the Lambda function code for usage calculator"""
    return '''
import re

def _resolve_model_id_from_arn(model_id_or_arn):
    """Resolve a model ID from an inference profile ARN or cross-region model ID.
    
    Handles:
    - Direct model IDs: anthropic.claude-3-sonnet-20240229-v1:0
    - Cross-region prefixed IDs: us.anthropic.claude-3-sonnet-20240229-v1:0
    - System inference profile ARNs: arn:aws:bedrock:us-east-1::foundation-model/...
    - Application inference profile ARNs: arn:aws:bedrock:us-east-1:123456789012:inference-profile/...
    - Cross-region inference profile ARNs: arn:aws:bedrock:us-east-1:123456789012:inference-profile/us.anthropic...
    
    Returns (resolved_model_id, original_model_id) tuple.
    The resolved ID is used for pricing lookup; the original is kept for tracking.
    """
    if not model_id_or_arn:
        return model_id_or_arn, model_id_or_arn
    
    original = model_id_or_arn
    resolved = model_id_or_arn
    
    # Handle ARN format
    if model_id_or_arn.startswith('arn:aws:bedrock:'):
        # Extract the resource part after the last ':'
        parts = model_id_or_arn.split(':')
        if len(parts) >= 6:
            resource = ':'.join(parts[5:])
            # foundation-model/anthropic.claude-3-sonnet-20240229-v1:0
            if resource.startswith('foundation-model/'):
                resolved = resource.replace('foundation-model/', '')
            # inference-profile/some-id or inference-profile/us.anthropic...
            elif resource.startswith('inference-profile/'):
                profile_id = resource.replace('inference-profile/', '')
                # If the profile ID looks like a model ID (contains a provider prefix), use it
                if '.' in profile_id and any(p in profile_id for p in ['anthropic', 'amazon', 'meta', 'mistral', 'cohere', 'ai21', 'stability', 'deepseek', 'google', 'qwen', 'writer', 'twelvelabs', 'luma', 'moonshotai', 'nvidia', 'openai', 'zai']):
                    resolved = profile_id
                else:
                    # Opaque profile ID — keep original for tracking, use as-is for pricing
                    resolved = profile_id
    
    # Strip cross-region prefix for pricing lookup (us.anthropic... -> anthropic...)
    # but keep the original for tracking
    cr_match = re.match(r'^(us|eu|ap|global|apac|au|ca|jp|us-gov)\\.(anthropic|amazon|meta|mistral|cohere|ai21|stability|deepseek|google|qwen|writer|twelvelabs|luma|moonshotai|nvidia|openai|zai)\\.(.*)', resolved)
    if cr_match:
        # Keep the cross-region ID as resolved — pricing_calculator handles both forms
        pass
    
    return resolved, original


def _extract_converse_token_usage(response_data):
    """Extract token usage from Converse/ConverseStream API response format.
    
    Converse API returns usage in response.usage:
    {
        "usage": {
            "inputTokens": 100,
            "outputTokens": 50,
            "totalTokens": 150,
            "cacheReadInputTokens": 0,
            "cacheWriteInputTokens": 0
        }
    }
    """
    usage = response_data.get('usage', {})
    if not usage and 'output' in response_data:
        usage = response_data.get('output', {}).get('usage', {})
    
    return {
        'input_tokens': usage.get('inputTokens', 0),
        'output_tokens': usage.get('outputTokens', 0),
        'cache_read_tokens': usage.get('cacheReadInputTokens', 0),
        'cache_creation_tokens': usage.get('cacheWriteInputTokens', 0),
    }


def _extract_request_metadata(log_data):
    """Extract requestMetadata from Converse API calls for custom attribution.
    
    The Converse API supports a requestMetadata field that appears in invocation logs,
    enabling custom cost attribution (userId, tenantId, projectId, etc.).
    """
    metadata = {}
    
    # Check in request parameters (CloudTrail format)
    request_params = log_data.get('requestParameters', {})
    if 'requestMetadata' in request_params:
        metadata = request_params['requestMetadata']
    
    # Check in input data (invocation log format)
    input_data = log_data.get('input', {})
    if 'requestMetadata' in input_data:
        metadata = input_data['requestMetadata']
    
    # Also check top-level (some log formats)
    if 'requestMetadata' in log_data:
        metadata = log_data['requestMetadata']
    
    return metadata


def _calculate_image_cost(model_id, image_count, resolution='1024x1024'):
    """Calculate cost for image generation models.
    
    Image models charge per image rather than per token.
    """
    # Image generation pricing (per image)
    image_pricing = {
        'stability.stable-diffusion-xl-v1': {'512x512': 0.018, '1024x1024': 0.036},
        'stability.sd3-large-v1:0': {'1024x1024': 0.035},
        'stability.stable-image-ultra-v1:0': {'1024x1024': 0.06},
        'stability.stable-image-core-v1:0': {'1024x1024': 0.04},
        'amazon.titan-image-generator-v1': {'512x512': 0.008, '1024x1024': 0.012},
        'amazon.titan-image-generator-v2:0': {'512x512': 0.008, '1024x1024': 0.012},
        'amazon.nova-canvas-v1:0': {'1024x1024': 0.04},
    }
    
    # Find matching pricing
    for key, prices in image_pricing.items():
        if key in model_id:
            price_per_image = prices.get(resolution, prices.get('1024x1024', 0.04))
            return price_per_image * image_count
    
    # Default image pricing
    return 0.04 * image_count


def _calculate_agent_flow_cost(event_name, detail):
    """Calculate cost for Bedrock Agents, Flows, and Knowledge Bases.
    
    - Agents: charged per token (model invocations) + orchestration
    - Flows: $0.035 per 1,000 node transitions
    - Knowledge Bases: charged per token for RetrieveAndGenerate, per query for Retrieve
    """
    cost = 0.0
    
    if event_name == 'InvokeFlow':
        # Flows charge $0.035 per 1,000 node transitions
        node_transitions = detail.get('responseElements', {}).get('nodeTransitions', 1)
        cost = (node_transitions / 1000) * 0.035
        
    elif event_name == 'Retrieve':
        # Knowledge Base retrieve — minimal cost, mainly for tracking
        # Actual cost is in the embedding model invocations
        cost = 0.0
        
    elif event_name in ('RetrieveAndGenerate', 'RetrieveAndGenerateStream'):
        # Knowledge Base RAG — token costs from the underlying model
        usage = detail.get('responseElements', {}).get('usage', {})
        input_tokens = usage.get('inputTokens', 0)
        output_tokens = usage.get('outputTokens', 0)
        model_id = detail.get('requestParameters', {}).get('modelId', '')
        if model_id and (input_tokens or output_tokens):
            cost = BedrockPricingCalculator.calculate_cost(model_id, input_tokens, output_tokens)

    elif event_name == 'InvokeAgent':
        # Agent invocations — token costs from underlying model
        usage = detail.get('responseElements', {}).get('usage', {})
        input_tokens = usage.get('inputTokens', 0)
        output_tokens = usage.get('outputTokens', 0)
        model_id = detail.get('requestParameters', {}).get('modelId', '')
        if model_id and (input_tokens or output_tokens):
            cost = BedrockPricingCalculator.calculate_cost(model_id, input_tokens, output_tokens)

    elif event_name == 'InvokeInlineAgent':
        # Inline agent invocations — uses 'foundationModel' instead of 'modelId'
        usage = detail.get('responseElements', {}).get('usage', {})
        input_tokens = usage.get('inputTokens', 0)
        output_tokens = usage.get('outputTokens', 0)
        model_id = detail.get('requestParameters', {}).get('foundationModel', '')
        if model_id and (input_tokens or output_tokens):
            cost = BedrockPricingCalculator.calculate_cost(model_id, input_tokens, output_tokens)

    return cost


def lambda_handler(event, context):
    """
    Process Bedrock invocation logs from Kinesis Data Firehose.
    Calculate token-based costs and update user budgets.
    Supports InvokeModel, Converse, Agents, Flows, image models, and batch inference.
    """
    logger.info(f"=== USAGE CALCULATOR LAMBDA STARTED ===")
    logger.info(f"Processing usage calculation event with {len(event.get('records', []))} records")
    
    processed_records = []
    
    try:
        for i, record in enumerate(event.get('records', [])):
            try:
                logger.info(f"=== PROCESSING RECORD {i+1}/{len(event.get('records', []))} ===")
                
                # Firehose base64 encodes data
                encoded_data = record['data']
                decoded_data = base64.b64decode(encoded_data)
                
                # Check if data is gzipped
                try:
                    decoded_data = gzip.decompress(decoded_data)
                except (gzip.BadGzipFile, OSError):
                    pass  # Not gzipped
                
                log_data_str = decoded_data.decode('utf-8')
                log_data = json.loads(log_data_str)
                
                # Process Bedrock invocation log
                result = process_bedrock_log(log_data)
                
                processed_records.append({
                    'recordId': record['recordId'],
                    'result': 'Ok' if result else 'ProcessingFailed'
                })
                
            except Exception as e:
                logger.error(f"Error processing record {record.get('recordId')}: {e}", exc_info=True)
                processed_records.append({
                    'recordId': record['recordId'],
                    'result': 'ProcessingFailed'
                })
        
        logger.info(f"=== USAGE CALCULATOR COMPLETED: {len(processed_records)} records ===")
        return {'records': processed_records}
        
    except Exception as e:
        logger.error(f"Error in usage calculator: {e}", exc_info=True)
        return {
            'records': [
                {'recordId': r['recordId'], 'result': 'ProcessingFailed'}
                for r in event.get('records', [])
            ]
        }

def process_bedrock_invocation_log(log_data):
    """Process CloudWatch Bedrock invocation log (direct from Bedrock service).
    Handles both legacy InvokeModel and Converse API log formats.
    """
    try:
        logger.info("=== PROCESSING BEDROCK INVOCATION LOG ===")
        
        input_data = log_data.get('input', {})
        output_data = log_data.get('output', {})
        
        output_tokens = 0
        input_tokens = 0
        cache_creation_tokens = 0
        cache_read_tokens = 0
        image_count = 0
        
        # Check if this is a Converse API log (has 'usage' at top level or in output)
        converse_usage = _extract_converse_token_usage(log_data)
        if converse_usage['input_tokens'] or converse_usage['output_tokens']:
            input_tokens = converse_usage['input_tokens']
            output_tokens = converse_usage['output_tokens']
            cache_read_tokens = converse_usage['cache_read_tokens']
            cache_creation_tokens = converse_usage['cache_creation_tokens']
            logger.info(f"Converse API token usage: input={input_tokens}, output={output_tokens}")
        else:
            # Legacy InvokeModel format — check outputBodyJson
            output_body = output_data.get('outputBodyJson', [])
            if output_body:
                for item in output_body:
                    if item.get('type') == 'message_start':
                        message = item.get('message', {})
                        usage = message.get('usage', {})
                        input_tokens = usage.get('input_tokens', 0)
                        cache_creation_tokens = usage.get('cache_creation_input_tokens', 0)
                        cache_read_tokens = usage.get('cache_read_input_tokens', 0)
                        output_tokens = usage.get('output_tokens', 0)
                        break
            
            # Fall back to top-level fields
            if input_tokens == 0 and output_tokens == 0:
                input_tokens = input_data.get('inputTokenCount', 0)
                cache_read_tokens = input_data.get('cacheReadInputTokenCount', 0)
                cache_creation_tokens = input_data.get('cacheWriteInputTokenCount', 0)
                output_tokens = output_data.get('outputTokenCount', 0)
                image_count = output_data.get('outputImageCount', 0)
        
        total_input_tokens = input_tokens + cache_read_tokens + cache_creation_tokens
        
        if total_input_tokens == 0 and output_tokens == 0 and image_count == 0:
            logger.warning("No token or image usage found in invocation log")
            return True
        
        # Extract and resolve model ID (handles inference profile ARNs)
        raw_model_id = log_data.get('modelId', '')
        if not raw_model_id and output_data.get('outputBodyJson'):
            for item in output_data['outputBodyJson']:
                if item.get('type') == 'message_start':
                    raw_model_id = item.get('message', {}).get('model', '')
                    break
        
        if not raw_model_id:
            logger.warning("No model ID found in invocation log")
            return True
        
        model_id, original_model_id = _resolve_model_id_from_arn(raw_model_id)
        
        # Extract requestMetadata from Converse API for custom attribution
        request_metadata = _extract_request_metadata(log_data)
        
        # Extract principal ID
        metadata = log_data.get('_metadata', {})
        principal_id = metadata.get('principal_id')
        
        # Check requestMetadata for custom user attribution
        if not principal_id and request_metadata:
            principal_id = request_metadata.get('userId') or request_metadata.get('tenantId')
        
        if not principal_id:
            identity = log_data.get('identity', {})
            identity_arn = identity.get('arn', '')
            if identity_arn and ':user/' in identity_arn:
                principal_id = identity_arn.split(':user/')[-1]
        
        if not principal_id:
            logger.warning("Could not extract principal ID from invocation log")
            return True
        
        # Calculate cost
        region = log_data.get('region', log_data.get('awsRegion', 'us-east-1'))
        
        if image_count > 0:
            cost = _calculate_image_cost(model_id, image_count)
            usage_type = 'bedrock_image_generation'
        else:
            cost = BedrockPricingCalculator.calculate_cost_with_cache(
                model_id, input_tokens, output_tokens,
                cache_creation_tokens, cache_read_tokens, region
            )
            usage_type = 'bedrock_invocation'
        
        # Record usage tracking
        record_usage_tracking(principal_id, model_id, cost, total_input_tokens, output_tokens,
                            usage_type, image_count=image_count, request_metadata=request_metadata,
                            original_model_id=original_model_id)
        
        # Update user budget
        update_user_budget(principal_id, model_id, cost, total_input_tokens, output_tokens)
        
        # Publish audit event
        event_detail = {
            'principal_id': principal_id,
            'model_id': model_id,
            'cost_usd': float(cost),
            'input_tokens': total_input_tokens,
            'output_tokens': output_tokens,
            'total_tokens': total_input_tokens + output_tokens,
            'usage_type': usage_type,
            'region': region,
        }
        if image_count > 0:
            event_detail['image_count'] = image_count
        if request_metadata:
            event_detail['request_metadata'] = request_metadata
        if original_model_id != model_id:
            event_detail['original_model_id'] = original_model_id
        
        EventPublisher.publish_budget_event('Usage Cost Calculated', event_detail)
        
        MetricsPublisher.publish_budget_metric(
            'TokensProcessed', total_input_tokens + output_tokens, 'Count',
            {'ModelId': model_id, 'PrincipalId': principal_id}
        )
        MetricsPublisher.publish_budget_metric(
            'CostCalculated', cost, 'None',
            {'ModelId': model_id, 'PrincipalId': principal_id}
        )
        if image_count > 0:
            MetricsPublisher.publish_budget_metric(
                'ImagesGenerated', image_count, 'Count',
                {'ModelId': model_id, 'PrincipalId': principal_id}
            )
        
        logger.info(f"Processed invocation for {principal_id}: {total_input_tokens}+{output_tokens} tokens, {image_count} images, cost=${cost:.6f}")
        return True
        
    except Exception as e:
        logger.error(f"Error processing Bedrock invocation log: {e}", exc_info=True)
        return False

def process_bedrock_log(log_data):
    """Process individual Bedrock log (handles CloudTrail API logs, CloudWatch invocation logs,
    Converse API logs, and Agent/Flow/KB events)."""
    try:
        actual_log_data = log_data
        
        # Handle wrapped log format
        if 'message' in log_data and isinstance(log_data['message'], str):
            try:
                actual_log_data = json.loads(log_data['message'])
                if '_metadata' in log_data:
                    actual_log_data['_metadata'] = log_data['_metadata']
            except json.JSONDecodeError:
                actual_log_data = log_data
        
        # CloudWatch invocation log format (has input/output structure)
        if 'input' in actual_log_data and 'output' in actual_log_data:
            return process_bedrock_invocation_log(actual_log_data)
        
        # CloudTrail API log format
        event_name = actual_log_data.get('eventName', '')
        
        # Supported API operations
        model_invocation_events = [
            'InvokeModel', 'InvokeModelWithResponseStream',
            'InvokeModelWithBidirectionalStream',
            'Converse', 'ConverseStream'
        ]
        agent_flow_events = [
            'InvokeAgent', 'InvokeInlineAgent', 'InvokeFlow',
            'Retrieve', 'RetrieveAndGenerate', 'RetrieveAndGenerateStream'
        ]
        batch_events = ['CreateModelInvocationJob', 'GetModelInvocationJob']
        async_events = ['StartAsyncInvoke']
        
        if event_name not in model_invocation_events + agent_flow_events + batch_events + async_events:
            return True  # Skip non-relevant events
        
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
        
        # Check requestMetadata for Converse API custom attribution
        request_metadata = _extract_request_metadata(actual_log_data)
        if not principal_id and request_metadata:
            principal_id = request_metadata.get('userId') or request_metadata.get('tenantId')
        
        if not principal_id:
            logger.warning(f"Could not extract principal ID from {event_name} log")
            return True
        
        region = actual_log_data.get('awsRegion', 'us-east-1')
        
        # Handle Agent/Flow/KB events
        if event_name in agent_flow_events:
            cost = _calculate_agent_flow_cost(event_name, actual_log_data)
            # InvokeInlineAgent uses 'foundationModel' instead of 'modelId'
            if event_name == 'InvokeInlineAgent':
                model_id = request_params.get('foundationModel', request_params.get('modelId', event_name))
            else:
                model_id = request_params.get('modelId', request_params.get('agentId', event_name))
            
            record_usage_tracking(principal_id, model_id, cost, 0, 0,
                                f'bedrock_{event_name.lower()}', request_metadata=request_metadata)
            if cost > 0:
                update_user_budget(principal_id, model_id, cost, 0, 0)
            
            EventPublisher.publish_budget_event('Usage Cost Calculated', {
                'principal_id': principal_id, 'model_id': model_id,
                'cost_usd': float(cost), 'usage_type': f'bedrock_{event_name.lower()}',
                'event_name': event_name, 'region': region,
            })
            return True
        
        # Handle batch inference events
        if event_name in batch_events:
            if event_name == 'CreateModelInvocationJob':
                model_id = request_params.get('modelId', '')
                record_usage_tracking(principal_id, model_id, 0, 0, 0,
                                    'bedrock_batch_submitted', request_metadata=request_metadata)
                EventPublisher.publish_budget_event('Batch Job Submitted', {
                    'principal_id': principal_id, 'model_id': model_id,
                    'job_name': request_params.get('jobName', ''),
                    'region': region,
                })
                MetricsPublisher.publish_budget_metric(
                    'BatchJobsSubmitted', 1, 'Count',
                    {'ModelId': model_id, 'Environment': os.environ['ENVIRONMENT']}
                )
            return True

        # Handle async invocation events (StartAsyncInvoke)
        if event_name in async_events:
            model_id = request_params.get('modelId', '')
            record_usage_tracking(principal_id, model_id, 0, 0, 0,
                                'bedrock_async_invocation', request_metadata=request_metadata)
            EventPublisher.publish_budget_event('Async Invocation Started', {
                'principal_id': principal_id, 'model_id': model_id,
                'event_name': event_name, 'region': region,
            })
            MetricsPublisher.publish_budget_metric(
                'AsyncInvocationsStarted', 1, 'Count',
                {'ModelId': model_id, 'Environment': os.environ['ENVIRONMENT']}
            )
            return True

        # Handle model invocation events (InvokeModel, Converse, etc.)
        raw_model_id = request_params.get('modelId', '')
        if not raw_model_id:
            logger.warning("No model ID found in request")
            return True
        
        model_id, original_model_id = _resolve_model_id_from_arn(raw_model_id)
        
        # Extract token usage — format differs between InvokeModel and Converse
        usage = response_elements.get('usage', {})
        input_tokens = usage.get('inputTokens', 0)
        output_tokens = usage.get('outputTokens', 0)
        cache_read_tokens = usage.get('cacheReadInputTokens', 0)
        cache_creation_tokens = usage.get('cacheWriteInputTokens', 0)
        image_count = response_elements.get('outputImageCount', usage.get('outputImageCount', 0))
        
        if input_tokens == 0 and output_tokens == 0 and image_count == 0:
            logger.warning(f"No usage found in {event_name} response")
            return True
        
        # Determine if batch inference (different pricing)
        is_batch = request_params.get('invocationType') == 'BATCH' or 'batch' in actual_log_data.get('eventSource', '').lower()
        
        # Calculate cost
        if image_count > 0:
            cost = _calculate_image_cost(model_id, image_count)
            usage_type = 'bedrock_image_generation'
        elif is_batch:
            # Batch inference typically 50% discount
            base_cost = BedrockPricingCalculator.calculate_cost_with_cache(
                model_id, input_tokens, output_tokens,
                cache_creation_tokens, cache_read_tokens, region
            )
            cost = base_cost * 0.5
            usage_type = 'bedrock_batch_inference'
        else:
            cost = BedrockPricingCalculator.calculate_cost_with_cache(
                model_id, input_tokens, output_tokens,
                cache_creation_tokens, cache_read_tokens, region
            )
            usage_type = f'cloudtrail_{event_name.lower()}'

        total_input = input_tokens + cache_read_tokens + cache_creation_tokens

        # --- AgentCore routing check ---
        # If the caller is an AssumedRole matching a registered AgentCore runtime,
        # attribute costs to that runtime's budget instead of API key budget.
        agentcore_table_name = os.environ.get('AGENTCORE_BUDGETS_TABLE', '')
        if agentcore_table_name and actual_log_data:
            caller_role_arn = extract_role_arn_from_event(actual_log_data)
            if caller_role_arn:
                runtime = lookup_runtime_by_role_arn(caller_role_arn)
                if runtime:
                    if cost and cost > 0:
                        update_runtime_budget(runtime['runtime_id'], cost)
                        update_global_pool(cost)
                        record_usage_tracking(runtime['runtime_id'], model_id, cost, total_input, output_tokens, 'agentcore')
                        logger.info(f"Attributed ${cost} to AgentCore runtime {runtime['runtime_id']}")
                        return True  # Cost attributed to AgentCore runtime; skip standard budget update

        # Look up team/purpose from budget record for usage tracking enrichment
        team_purpose = _get_key_metadata(principal_id) if principal_id.startswith('BedrockAPIKey-') else {}

        record_usage_tracking(principal_id, model_id, cost, total_input, output_tokens,
                            usage_type, image_count=image_count, request_metadata=request_metadata,
                            original_model_id=original_model_id, team=team_purpose.get('team'),
                            purpose=team_purpose.get('purpose'))
        update_user_budget(principal_id, model_id, cost, total_input, output_tokens)

        # Update pool spent if this is an unbudgeted API key
        if principal_id.startswith('BedrockAPIKey-') and cost and cost > 0:
            _update_api_key_pool_if_needed(principal_id, cost, team_purpose)
        
        event_detail = {
            'principal_id': principal_id, 'model_id': model_id,
            'cost_usd': float(cost), 'input_tokens': total_input,
            'output_tokens': output_tokens, 'total_tokens': total_input + output_tokens,
            'usage_type': usage_type, 'region': region,
        }
        if image_count > 0:
            event_detail['image_count'] = image_count
        if request_metadata:
            event_detail['request_metadata'] = request_metadata
        if original_model_id != model_id:
            event_detail['original_model_id'] = original_model_id
        if is_batch:
            event_detail['is_batch'] = True
        
        EventPublisher.publish_budget_event('Usage Cost Calculated', event_detail)
        
        MetricsPublisher.publish_budget_metric(
            'TokensProcessed', total_input + output_tokens, 'Count',
            {'ModelId': model_id, 'PrincipalId': principal_id}
        )
        MetricsPublisher.publish_budget_metric(
            'CostCalculated', cost, 'None',
            {'ModelId': model_id, 'PrincipalId': principal_id}
        )
        
        return True
        
    except Exception as e:
        logger.error(f"Error processing Bedrock log: {e}", exc_info=True)
        return False


def record_usage_tracking(principal_id, model_id, cost, input_tokens, output_tokens,
                         usage_type, image_count=0, request_metadata=None, original_model_id=None,
                         team=None, purpose=None, region=None):
    """Record usage data in the usage tracking table"""
    try:
        usage_tracking_table = dynamodb.Table(os.environ['USAGE_TRACKING_TABLE'])
        current_time = datetime.now(timezone.utc)
        
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
            'region': region or os.environ.get('AWS_REGION', 'us-east-1'),
            'created_epoch': int(current_time.timestamp())
        }
        
        if image_count > 0:
            usage_record['image_count'] = image_count
        if request_metadata:
            usage_record['request_metadata'] = request_metadata
        if original_model_id and original_model_id != model_id:
            usage_record['original_model_id'] = original_model_id
        if team:
            usage_record['team'] = team
        if purpose:
            usage_record['purpose'] = purpose

        usage_tracking_table.put_item(Item=usage_record)
        logger.info(f"Recorded usage for {principal_id}: {usage_type}, ${cost:.6f}")
        
    except Exception as e:
        logger.error(f"Error recording usage tracking for {principal_id}: {e}")

def update_user_budget(principal_id, model_id, cost, input_tokens, output_tokens):
    """Update user budget with new spending"""
    try:
        user_budgets_table = dynamodb.Table(os.environ['USER_BUDGETS_TABLE'])
        current_time = datetime.now(timezone.utc)
        
        try:
            response = user_budgets_table.update_item(
                Key={'principal_id': principal_id},
                UpdateExpression="SET spent_usd = if_not_exists(spent_usd, :zero) + :cost, last_updated_epoch = :timestamp, model_spend_breakdown.#model_id = if_not_exists(model_spend_breakdown.#model_id, :zero) + :cost",
                ExpressionAttributeNames={'#model_id': model_id},
                ExpressionAttributeValues={
                    ':cost': Decimal(str(cost)),
                    ':timestamp': int(current_time.timestamp()),
                    ':zero': Decimal('0.0')
                },
                ReturnValues='ALL_NEW'
            )
        except Exception as update_error:
            logger.error(f"Failed to update budget for {principal_id}: {update_error}")
            try:
                create_basic_budget_record(principal_id, cost, model_id, current_time)
                return
            except Exception as create_error:
                logger.error(f"Failed to create budget record for {principal_id}: {create_error}")
                raise update_error
        
        # Check budget thresholds (only for keys with a per-key carve-out)
        # Pool-based keys have no budget_limit_usd — their enforcement is in budget_monitor
        updated_item = response['Attributes']
        spent_usd = float(updated_item['spent_usd'])
        budget_limit_raw = updated_item.get('budget_limit_usd')

        if budget_limit_raw is not None and updated_item.get('has_carveout'):
            budget_limit_usd = float(budget_limit_raw)

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

            if new_threshold_state != current_threshold_state:
                user_budgets_table.update_item(
                    Key={'principal_id': principal_id},
                    UpdateExpression='SET threshold_state = :state',
                    ExpressionAttributeValues={':state': new_threshold_state}
                )
                EventPublisher.publish_budget_event('Budget Threshold Changed', {
                    'principal_id': principal_id,
                    'previous_state': current_threshold_state,
                    'new_state': new_threshold_state,
                    'spent_usd': spent_usd,
                    'budget_limit_usd': budget_limit_usd,
                    'percent_used': (spent_usd / budget_limit_usd) * 100
                })
        
    except Exception as e:
        logger.error(f"Error updating user budget for {principal_id}: {e}")
        raise

def create_basic_budget_record(principal_id, initial_cost, model_id, current_time):
    """Create a basic budget record when one does not exist"""
    try:
        user_budgets_table = dynamodb.Table(os.environ['USER_BUDGETS_TABLE'])
        
        default_budget = ConfigurationManager.get_parameter(
            '/bedrock-budgeteer/global/default_user_budget_usd', 5.0
        )
        env = os.environ.get('ENVIRONMENT', 'production')
        refresh_period_days = ConfigurationManager.get_parameter(
            f'/bedrock-budgeteer/{env}/cost/budget_refresh_period_days', 30
        )
        refresh_date = current_time + timedelta(days=int(refresh_period_days))
        
        budget_item = {
            'principal_id': principal_id,
            'account_type': 'bedrock_api_key',
            'budget_limit_usd': Decimal(str(default_budget)),
            'spent_usd': Decimal(str(initial_cost)),
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
            'auto_created': True
        }
        
        user_budgets_table.put_item(
            Item=budget_item,
            ConditionExpression='attribute_not_exists(principal_id)'
        )
        
        logger.info(f"Created budget record for {principal_id} with initial cost ${initial_cost:.6f}")
        
        EventPublisher.publish_budget_event('Budget Auto-Created', {
            'principal_id': principal_id,
            'account_type': 'bedrock_api_key',
            'budget_limit_usd': float(default_budget),
            'initial_cost': float(initial_cost),
            'model_id': model_id,
            'reason': 'usage_detected_without_existing_budget'
        })
        
    except Exception as e:
        logger.error(f"Error creating budget record for {principal_id}: {e}")
        raise


# Module-level cache for key metadata (survives across Lambda invocations)
# Bounded to 500 entries with time-based expiry (5 min) to prevent memory leaks
# and stale data from persisting across budget tier changes
_key_metadata_cache = {}
_KEY_METADATA_CACHE_MAX_SIZE = 500
_KEY_METADATA_CACHE_TTL_SECONDS = 300

def _get_key_metadata(principal_id):
    """Get team/purpose/has_carveout from user_budgets record (cached with TTL)"""
    import time as _time
    cached = _key_metadata_cache.get(principal_id)
    if cached and (_time.time() - cached.get('_cached_at', 0)) < _KEY_METADATA_CACHE_TTL_SECONDS:
        return cached

    try:
        user_budgets_table = dynamodb.Table(os.environ['USER_BUDGETS_TABLE'])
        response = user_budgets_table.get_item(
            Key={'principal_id': principal_id},
            ProjectionExpression='team, purpose, has_carveout'
        )
        item = response.get('Item', {})
        import time as _time
        metadata = {
            'team': item.get('team'),
            'purpose': item.get('purpose'),
            'has_carveout': item.get('has_carveout', False),
            '_cached_at': _time.time()
        }
        # Evict oldest entry if cache is full (avoid thundering herd from clear())
        if len(_key_metadata_cache) >= _KEY_METADATA_CACHE_MAX_SIZE:
            oldest_key = next(iter(_key_metadata_cache))
            del _key_metadata_cache[oldest_key]
        _key_metadata_cache[principal_id] = metadata
        return metadata
    except Exception as e:
        logger.warning(f"Could not fetch metadata for {principal_id}: {e}")
        return {}


def _update_api_key_pool_if_needed(principal_id, cost, metadata):
    """If this principal is an unbudgeted API key, also update the global pool spent"""
    if metadata.get('has_carveout', False):
        return  # Budgeted keys don't affect the pool

    try:
        user_budgets_table = dynamodb.Table(os.environ['USER_BUDGETS_TABLE'])
        user_budgets_table.update_item(
            Key={'principal_id': 'GLOBAL_API_KEY_POOL'},
            UpdateExpression='SET spent_usd = if_not_exists(spent_usd, :zero) + :cost',
            ExpressionAttributeValues={
                ':cost': Decimal(str(cost)),
                ':zero': Decimal('0')
            }
        )
    except Exception as e:
        logger.warning(f"Could not update API key pool for {principal_id}: {e}")
'''
