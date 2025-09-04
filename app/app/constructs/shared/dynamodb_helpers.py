"""
DynamoDB Helpers
Helper functions for DynamoDB operations
"""
from decimal import Decimal
from typing import Dict, Any, List, Union


class DynamoDBHelper:
    """Helper functions for DynamoDB operations"""
    
    @staticmethod
    def decimal_to_float(obj: Union[Dict, List, Any]) -> Any:
        """Convert DynamoDB Decimal objects to float"""
        if isinstance(obj, Decimal):
            return float(obj)
        elif isinstance(obj, dict):
            return {k: DynamoDBHelper.decimal_to_float(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [DynamoDBHelper.decimal_to_float(item) for item in obj]
        return obj
    
    @staticmethod
    def float_to_decimal(obj: Union[Dict, List, Any]) -> Any:
        """Convert float objects to DynamoDB Decimal"""
        if isinstance(obj, (int, float)):
            return Decimal(str(obj))
        elif isinstance(obj, dict):
            return {k: DynamoDBHelper.float_to_decimal(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [DynamoDBHelper.float_to_decimal(item) for item in obj]
        return obj
