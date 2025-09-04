"""
Configuration Manager
Manages SSM parameter configuration with caching
"""
import json
import boto3
import logging
from typing import Dict, Any

logger = logging.getLogger()

# AWS clients will be initialized lazily


class ConfigurationManager:
    """Manages SSM parameter configuration"""
    
    _cache = {}
    
    @classmethod
    def get_parameter(cls, parameter_name: str, default_value: Any = None) -> Any:
        """Get parameter from SSM Parameter Store with caching"""
        if parameter_name in cls._cache:
            return cls._cache[parameter_name]
        
        try:
            ssm = boto3.client('ssm')
            response = ssm.get_parameter(Name=parameter_name)
            value = response['Parameter']['Value']
            
            # Try to parse as JSON, fall back to string
            try:
                value = json.loads(value)
            except json.JSONDecodeError:
                pass
            
            cls._cache[parameter_name] = value
            return value
        except Exception as e:
            logger.warning(f"Failed to get parameter {parameter_name}: {e}")
            return default_value
    
    @classmethod
    def get_budget_thresholds(cls) -> Dict[str, float]:
        """Get budget threshold configuration"""
        return {
            'warn_percent': cls.get_parameter('/bedrock-budgeteer/global/thresholds_percent_warn', 70.0),
            'critical_percent': cls.get_parameter('/bedrock-budgeteer/global/thresholds_percent_critical', 90.0)
        }
