"""
Configuration Management Construct for Bedrock Budgeteer
Manages SSM Parameter Store hierarchy and application configuration
"""
from typing import Dict, Optional
from aws_cdk import (
    aws_ssm as ssm,
    aws_kms as kms,
)
from constructs import Construct


class ConfigurationConstruct(Construct):
    """Construct for managing application configuration via SSM Parameter Store"""
    
    def __init__(self, scope: Construct, construct_id: str, 
                 environment_name: str, kms_key: Optional[kms.Key] = None, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)
        
        self.environment_name = environment_name
        self.kms_key = kms_key
        self.parameters: Dict[str, ssm.StringParameter] = {}
        
        # Create parameter hierarchy - only parameters that are actually used
        self._create_cost_config()  # Only budget_refresh_period_days is used
        self._create_global_config()  # Thresholds, budgets, and control flags
        self._create_monitoring_config()  # Log retention and monitoring settings
        
        # Tags are applied by TaggingFramework aspects
    
    def _get_parameter_name(self, category: str, key: str) -> str:
        """Generate standardized parameter name"""
        return f"/bedrock-budgeteer/{self.environment_name}/{category}/{key}"
    
    def _get_global_parameter_name(self, category: str, key: str) -> str:
        """Generate global parameter name (without environment)"""
        return f"/bedrock-budgeteer/{category}/{key}"
    
    def _create_secure_parameter(self, category: str, key: str, value: str, 
                               description: str) -> ssm.StringParameter:
        """Create a secure string parameter with KMS encryption"""
        parameter_name = self._get_parameter_name(category, key)
        
        param_props = {
            "parameter_name": parameter_name,
            "string_value": value,
            "description": description,
            "tier": ssm.ParameterTier.STANDARD
        }
        
        # Use custom KMS key if provided
        if self.kms_key:
            param_props["encryption_key"] = self.kms_key
        
        return ssm.StringParameter(
            self, f"{category.title()}{key.title()}Parameter",
            **param_props
        )
    
    def _create_standard_parameter(self, category: str, key: str, value: str,
                                 description: str) -> ssm.StringParameter:
        """Create a standard string parameter"""
        parameter_name = self._get_parameter_name(category, key)
        
        return ssm.StringParameter(
            self, f"{category.title()}{key.title()}Parameter",
            parameter_name=parameter_name,
            string_value=value,
            description=description,
            tier=ssm.ParameterTier.STANDARD
        )
    
    def _create_global_parameter(self, category: str, key: str, value: str,
                               description: str) -> ssm.StringParameter:
        """Create a global parameter (accessible across environments)"""
        parameter_name = self._get_global_parameter_name(category, key)
        
        return ssm.StringParameter(
            self, f"Global{category.title()}{key.title()}Parameter",
            parameter_name=parameter_name,
            string_value=value,
            description=description,
            tier=ssm.ParameterTier.STANDARD
        )
    
    # Removed _create_application_config - all parameters were unused
    
    # Removed _create_security_config - all parameters were unused
    
    def _create_monitoring_config(self) -> None:
        """Create monitoring configuration parameters"""
        monitoring_config = self._get_monitoring_config()
        
        for key, config in monitoring_config.items():
            self.parameters[f"monitoring_{key}"] = self._create_standard_parameter(
                category="monitoring",
                key=key,
                value=config["value"],
                description=config["description"]
            )
    
    # Removed _create_integration_config - all parameters were unused
    
    def _create_cost_config(self) -> None:
        """Create cost and budget configuration parameters"""
        cost_config = self._get_cost_config()
        
        for key, config in cost_config.items():
            self.parameters[f"cost_{key}"] = self._create_standard_parameter(
                category="cost",
                key=key,
                value=config["value"],
                description=config["description"]
            )
    
    # Removed _get_application_config - all parameters were unused
    
    # Removed _get_security_config - all parameters were unused
    
    def _get_monitoring_config(self) -> Dict[str, Dict[str, str]]:
        """Get monitoring configuration - log retention and monitoring settings"""
        monitoring_config = {
            "log_retention_days": {
                "value": "7",
                "description": "CloudWatch log group retention period in days"
            }
        }
        
        return monitoring_config
    
    # Removed _get_integration_config - all parameters were unused
    
    def _get_cost_config(self) -> Dict[str, Dict[str, str]]:
        """Get cost and budget configuration - only used parameters"""
        cost_config = {
            "budget_refresh_period_days": {
                "value": "30",
                "description": "Budget refresh period in days (resets budget and counters)"
            }
        }
        
        return cost_config
    
    # Removed _create_workflow_config - all parameters were unused
    
    def _create_global_config(self) -> None:
        """Create global system configuration parameters"""
        global_config = self._get_global_config()
        
        for key, config in global_config.items():
            self.parameters[f"global_{key}"] = self._create_global_parameter(
                category="global",
                key=key,
                value=config["value"],
                description=config["description"]
            )
    
    # Removed _get_workflow_config - all parameters were unused
    
    def _get_global_config(self) -> Dict[str, Dict[str, str]]:
        """Get global system configuration - only used parameters"""
        global_config = {
            # Budget thresholds (used in ConfigurationManager)
            "thresholds_percent_warn": {
                "value": "70",
                "description": "Budget warning threshold percentage"
            },
            "thresholds_percent_critical": {
                "value": "90",
                "description": "Budget critical threshold percentage"
            },
            # Default budget (used in user setup and usage calculator)
            "default_user_budget_usd": {
                "value": "1",  # Testing default
                "description": "Default budget limit for users in USD"
            },
            # Grace period for budget violations (configurable for different environments)
            "grace_period_seconds": {
                "value": "300",  # Default 5 minutes for production
                "description": "Grace period in seconds before suspending users who exceed budget (300s = 5 minutes)"
            }
        }
        
        return global_config
    
    # Removed _get_max_budget_value - no longer needed
    
    def get_parameter_reference(self, category: str, key: str) -> str:
        """Get SSM parameter reference for use in other constructs"""
        return self._get_parameter_name(category, key)
    
    def create_custom_parameter(self, category: str, key: str, value: str,
                              description: str, secure: bool = False) -> ssm.StringParameter:
        """Create a custom parameter in the hierarchy"""
        if secure:
            parameter = self._create_secure_parameter(category, key, value, description)
        else:
            parameter = self._create_standard_parameter(category, key, value, description)
        
        self.parameters[f"{category}_{key}"] = parameter
        return parameter
    

