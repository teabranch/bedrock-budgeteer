"""
Bedrock Pricing Calculator
Calculates costs for Bedrock model usage using DynamoDB pricing table
"""
import json
import os
import boto3
import logging

from typing import Dict, Any, Optional
from datetime import datetime, timezone

logger = logging.getLogger()

# AWS clients will be initialized lazily in the BedrockPricingCalculator class


class BedrockPricingCalculator:
    """Calculates costs for Bedrock model usage using DynamoDB pricing table"""
    
    # Local cache for pricing data (short-term cache to avoid repeated DynamoDB queries)
    _local_cache = {}
    _cache_timestamp = None
    _cache_ttl = 300  # 5 minutes local cache
    
    @classmethod
    def get_model_pricing(cls, model_id: str, region: str = 'us-east-1') -> Dict[str, float]:
        """Get pricing for a specific Bedrock model from DynamoDB"""
        cache_key = f"{model_id}-{region}"
        current_time = datetime.now(timezone.utc)
        
        # Check local cache validity (5 minutes)
        if (cls._cache_timestamp and 
            (current_time - cls._cache_timestamp).total_seconds() < cls._cache_ttl and
            cache_key in cls._local_cache):
            logger.info(f"Using local cache for {model_id} pricing")
            return cls._local_cache[cache_key]
        
        try:
            # Query DynamoDB pricing table
            dynamodb = boto3.resource('dynamodb')
            pricing_table = dynamodb.Table(os.environ['PRICING_TABLE'])
            
            logger.info(f"Querying pricing table for model={model_id}, region={region}")
            response = pricing_table.get_item(
                Key={
                    'model_id': model_id,
                    'region': region
                }
            )
            
            if 'Item' in response:
                item = response['Item']
                pricing_data = {
                    'input_tokens_per_1000': float(item['input_tokens_per_1000']),
                    'output_tokens_per_1000': float(item['output_tokens_per_1000'])
                }
                
                logger.info(f"Retrieved pricing from DynamoDB for {model_id}: input=${pricing_data['input_tokens_per_1000']:.6f}, output=${pricing_data['output_tokens_per_1000']:.6f} per 1K tokens")
                
                # Cache locally
                cls._local_cache[cache_key] = pricing_data
                cls._cache_timestamp = current_time
                
                return pricing_data
            else:
                logger.warning(f"No pricing data found in DynamoDB for {model_id} in {region}, using fallback")
                return cls._get_fallback_pricing(model_id)
            
        except Exception as e:
            logger.error(f"Failed to get pricing from DynamoDB for {model_id}: {e}")
            return cls._get_fallback_pricing(model_id)
    
    @classmethod
    def fetch_pricing_from_api(cls, model_id: str, region: str = 'us-east-1') -> Optional[Dict[str, float]]:
        """Fetch pricing from AWS Pricing API for a specific Bedrock model"""
        try:
            pricing_client = boto3.client('pricing', region_name='us-east-1')  # Pricing API only in us-east-1
            
            # Extract service and model info from model_id
            service_code = 'AmazonBedrock'
            
            # Map model ID to product family and instance type for the API
            model_filters = [
                {
                    'Type': 'TERM_MATCH',
                    'Field': 'servicecode',
                    'Value': service_code
                },
                {
                    'Type': 'TERM_MATCH',
                    'Field': 'location',
                    'Value': 'US East (N. Virginia)' if region == 'us-east-1' else f'US West (Oregon)' if region == 'us-west-2' else 'US East (N. Virginia)'
                }
            ]
            
            # Add model-specific filters based on model_id
            if 'claude-3-opus' in model_id:
                model_filters.append({
                    'Type': 'TERM_MATCH',
                    'Field': 'productFamily',
                    'Value': 'Bedrock Model Inference'
                })
            elif 'claude-3-sonnet' in model_id or 'claude-3-5-sonnet' in model_id:
                model_filters.append({
                    'Type': 'TERM_MATCH',
                    'Field': 'productFamily', 
                    'Value': 'Bedrock Model Inference'
                })
            elif 'claude-3-haiku' in model_id or 'claude-3-5-haiku' in model_id:
                model_filters.append({
                    'Type': 'TERM_MATCH',
                    'Field': 'productFamily',
                    'Value': 'Bedrock Model Inference'
                })
            
            logger.info(f"Fetching pricing from AWS API for model {model_id} in region {region}")
            
            response = pricing_client.get_products(
                ServiceCode=service_code,
                Filters=model_filters,
                MaxResults=100
            )
            
            pricing_data = cls._parse_pricing_response(response, model_id)
            if pricing_data:
                logger.info(f"Successfully fetched pricing from AWS API for {model_id}: input=${pricing_data['input_tokens_per_1000']:.6f}, output=${pricing_data['output_tokens_per_1000']:.6f}")
                return pricing_data
            else:
                logger.warning(f"Could not parse pricing data from AWS API for {model_id}")
                return None
                
        except Exception as e:
            logger.error(f"Failed to fetch pricing from AWS API for {model_id}: {e}")
            return None
    
    @classmethod
    def _parse_pricing_response(cls, response: Dict[str, Any], model_id: str) -> Optional[Dict[str, float]]:
        """Parse AWS Pricing API response to extract per-token rates"""
        try:
            price_list = response.get('PriceList', [])
            if not price_list:
                return None
            
            input_rate = None
            output_rate = None
            
            for price_item_str in price_list:
                price_item = json.loads(price_item_str)
                
                # Extract product attributes
                product = price_item.get('product', {})
                attributes = product.get('attributes', {})
                
                # Check if this is the correct model and get usage type
                usage_type = attributes.get('usageType', '')
                operation = attributes.get('operation', '')
                
                logger.info(f"Processing price item: usageType={usage_type}, operation={operation}")
                
                # Parse terms to get actual pricing
                terms = price_item.get('terms', {})
                on_demand = terms.get('OnDemand', {})
                
                if on_demand:
                    for term_key, term_data in on_demand.items():
                        price_dimensions = term_data.get('priceDimensions', {})
                        for dim_key, dim_data in price_dimensions.items():
                            price_per_unit = float(dim_data.get('pricePerUnit', {}).get('USD', 0))
                            unit = dim_data.get('unit', '')
                            description = dim_data.get('description', '')
                            
                            logger.info(f"Price dimension: {description}, unit={unit}, price=${price_per_unit}")
                            
                            # Identify input vs output tokens based on description/operation
                            if 'input' in description.lower() or 'Input' in operation:
                                input_rate = price_per_unit
                            elif 'output' in description.lower() or 'Output' in operation:
                                output_rate = price_per_unit
            
            if input_rate is not None and output_rate is not None:
                return {
                    'input_tokens_per_1000': input_rate,
                    'output_tokens_per_1000': output_rate
                }
            else:
                logger.warning(f"Could not find both input and output rates. input_rate={input_rate}, output_rate={output_rate}")
                return None
                
        except Exception as e:
            logger.error(f"Error parsing pricing response: {e}")
            return None
    
    @classmethod
    def _get_fallback_pricing(cls, model_id: str) -> Dict[str, float]:
        """Get model-specific fallback pricing when API fails"""
        # Updated fallback pricing based on current AWS Bedrock rates (as of 2024-2025)
        model_pricing = {
            # Claude 3 Family
            'anthropic.claude-3-opus-20240229-v1:0': {
                'input_tokens_per_1000': 0.015,    # $15/1M tokens
                'output_tokens_per_1000': 0.075    # $75/1M tokens  
            },
            'anthropic.claude-3-sonnet-20240229-v1:0': {
                'input_tokens_per_1000': 0.003,    # $3/1M tokens
                'output_tokens_per_1000': 0.015    # $15/1M tokens
            },
            'anthropic.claude-3-haiku-20240307-v1:0': {
                'input_tokens_per_1000': 0.00025,  # $0.25/1M tokens
                'output_tokens_per_1000': 0.00125  # $1.25/1M tokens
            },
            
            # Claude 3.5 Family  
            'anthropic.claude-3-5-sonnet-20240620-v1:0': {
                'input_tokens_per_1000': 0.003,    # $3/1M tokens
                'output_tokens_per_1000': 0.015    # $15/1M tokens
            },
            'anthropic.claude-3-5-sonnet-20241022-v2:0': {
                'input_tokens_per_1000': 0.003,    # $3/1M tokens
                'output_tokens_per_1000': 0.015    # $15/1M tokens
            },
            'anthropic.claude-3-5-haiku-20241022-v1:0': {
                'input_tokens_per_1000': 0.001,    # $1/1M tokens
                'output_tokens_per_1000': 0.005    # $5/1M tokens
            },
            
            # Claude 4 Family (Updated with official pricing as of 02.09.2025)
            'anthropic.claude-opus-4-20250115-v1:0': {
                'input_tokens_per_1000': 0.015,    # $15/1M tokens
                'output_tokens_per_1000': 0.075    # $75/1M tokens
            },
            'anthropic.claude-opus-4-1-20250115-v1:0': {
                'input_tokens_per_1000': 0.015,    # $15/1M tokens
                'output_tokens_per_1000': 0.075    # $75/1M tokens
            },
            'anthropic.claude-sonnet-4-20250115-v1:0': {
                'input_tokens_per_1000': 0.003,    # $3/1M tokens
                'output_tokens_per_1000': 0.015    # $15/1M tokens
            },
            'anthropic.claude-sonnet-4-long-context-20250115-v1:0': {
                'input_tokens_per_1000': 0.006,    # $6/1M tokens
                'output_tokens_per_1000': 0.0225   # $22.5/1M tokens
            },
            # Legacy format for Claude 4 (Sonnet) - keeping for backwards compatibility
            'claude-sonnet-4-20250514': {
                'input_tokens_per_1000': 0.003,    # $3/1M tokens
                'output_tokens_per_1000': 0.015    # $15/1M tokens
            },
            
            # Additional model patterns with regional variations
            'us.anthropic.claude-3-5-sonnet-20241022-v2:0': {
                'input_tokens_per_1000': 0.003,    # $3/1M tokens
                'output_tokens_per_1000': 0.015    # $15/1M tokens
            },
            'us.anthropic.claude-sonnet-4-20250115-v1:0': {
                'input_tokens_per_1000': 0.003,    # $3/1M tokens
                'output_tokens_per_1000': 0.015    # $15/1M tokens
            },
            'us.anthropic.claude-opus-4-20250115-v1:0': {
                'input_tokens_per_1000': 0.015,    # $15/1M tokens
                'output_tokens_per_1000': 0.075    # $75/1M tokens
            },
            'us.anthropic.claude-opus-4-1-20250115-v1:0': {
                'input_tokens_per_1000': 0.015,    # $15/1M tokens
                'output_tokens_per_1000': 0.075    # $75/1M tokens
            },
            'us.anthropic.claude-sonnet-4-long-context-20250115-v1:0': {
                'input_tokens_per_1000': 0.006,    # $6/1M tokens
                'output_tokens_per_1000': 0.0225   # $22.5/1M tokens
            },
            # Legacy format for Claude 4 (Sonnet) - keeping for backwards compatibility 
            'us.anthropic.claude-sonnet-4-20250514-v1:0': {
                'input_tokens_per_1000': 0.003,    # $3/1M tokens
                'output_tokens_per_1000': 0.015    # $15/1M tokens
            }
        }
        
        # Extract model name from full ARN if needed
        model_key = model_id
        for key in model_pricing.keys():
            if key in model_id:
                model_key = key
                break
        
        fallback = model_pricing.get(model_key, {
            'input_tokens_per_1000': 0.003,  # Default to Claude Sonnet pricing
            'output_tokens_per_1000': 0.015
        })
        
        logger.warning(f"Using fallback pricing for {model_id}: input=${fallback['input_tokens_per_1000']:.6f}, output=${fallback['output_tokens_per_1000']:.6f} per 1K tokens")
        return fallback
    
    @classmethod
    def calculate_cost(cls, model_id: str, input_tokens: int, output_tokens: int, region: str = 'us-east-1') -> float:
        """Calculate total cost for model usage"""
        pricing = cls.get_model_pricing(model_id, region)
        
        input_cost = (input_tokens / 1000) * pricing['input_tokens_per_1000']
        output_cost = (output_tokens / 1000) * pricing['output_tokens_per_1000']
        
        total_cost = input_cost + output_cost
        
        logger.info(f"Cost calculation for {model_id}: {input_tokens} input tokens = ${input_cost:.6f}, {output_tokens} output tokens = ${output_cost:.6f}, total = ${total_cost:.6f}")
        
        return total_cost
    
    @classmethod
    def calculate_cost_with_cache(cls, model_id: str, input_tokens: int, output_tokens: int, 
                                cache_creation_tokens: int = 0, cache_read_tokens: int = 0, 
                                region: str = 'us-east-1') -> float:
        """Calculate total cost including cache token operations"""
        pricing = cls.get_model_pricing(model_id, region)
        
        # Regular input and output costs
        input_cost = (input_tokens / 1000) * pricing['input_tokens_per_1000']
        output_cost = (output_tokens / 1000) * pricing['output_tokens_per_1000']
        
        # Cache operations: cache creation is charged at input rate, cache read at discounted rate
        cache_creation_cost = (cache_creation_tokens / 1000) * pricing['input_tokens_per_1000']
        # Cache read tokens are typically charged at 10% of input rate
        cache_read_cost = (cache_read_tokens / 1000) * (pricing['input_tokens_per_1000'] * 0.1)
        
        total_cost = input_cost + output_cost + cache_creation_cost + cache_read_cost
        
        logger.info(f"Cost calculation with cache for {model_id}: ")
        logger.info(f"  - {input_tokens} input tokens = ${input_cost:.6f}")
        logger.info(f"  - {output_tokens} output tokens = ${output_cost:.6f}")
        logger.info(f"  - {cache_creation_tokens} cache creation tokens = ${cache_creation_cost:.6f}")
        logger.info(f"  - {cache_read_tokens} cache read tokens = ${cache_read_cost:.6f}")
        logger.info(f"  - Total cost = ${total_cost:.6f}")
        
        return total_cost
