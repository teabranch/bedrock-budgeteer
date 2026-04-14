"""
Configuration Manager
Manages SSM parameter configuration with caching and TTL
"""
import json
import time
import boto3
import logging
from typing import Dict, Any, Tuple

logger = logging.getLogger()

_CACHE_TTL_SECONDS = 300  # 5 minutes


class ConfigurationManager:
    """Manages SSM parameter configuration with time-based cache expiry"""

    _cache: Dict[str, Tuple[Any, float]] = {}  # {param_name: (value, expiry_epoch)}

    @classmethod
    def get_parameter(cls, parameter_name: str, default_value: Any = None) -> Any:
        """Get parameter from SSM Parameter Store with caching (5-min TTL)"""
        cached = cls._cache.get(parameter_name)
        if cached is not None:
            value, expiry = cached
            if time.time() < expiry:
                return value
            # Expired — fall through to refresh

        try:
            ssm = boto3.client('ssm')
            response = ssm.get_parameter(Name=parameter_name)
            value = response['Parameter']['Value']

            # Try to parse as JSON, fall back to string
            try:
                value = json.loads(value)
            except json.JSONDecodeError:
                pass

            cls._cache[parameter_name] = (value, time.time() + _CACHE_TTL_SECONDS)
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
