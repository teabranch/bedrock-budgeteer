"""
Data Storage Construct for Bedrock Budgeteer
Manages DynamoDB tables and related storage resources
"""
from typing import Dict, Any, Optional
from aws_cdk import (
    aws_dynamodb as dynamodb,
    aws_kms as kms,
    RemovalPolicy,
    Duration,
)
from constructs import Construct


class DataStorageConstruct(Construct):
    """Construct for DynamoDB tables and data storage resources"""
    
    def __init__(self, scope: Construct, construct_id: str, 
                 environment_name: str, 
                 kms_key: Optional[kms.IKey] = None,
                 **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)
        
        self.environment_name = environment_name
        self.kms_key = kms_key  # User-provided KMS key (optional)
        self.tables: Dict[str, dynamodb.Table] = {}
        
        # Configuration
        self.removal_policy = self._get_removal_policy()
        self.billing_mode = self._get_billing_mode()
        
        # Create DynamoDB tables
        self._create_user_budget_table()
        self._create_usage_tracking_table()
        self._create_audit_logs_table()
        self._create_pricing_table()
        
        # Tags are applied by TaggingFramework aspects
    
    def _get_removal_policy(self) -> RemovalPolicy:
        """Get removal policy for production environment"""
        # Allow resource deletion for proper rollback during deployment failures
        return RemovalPolicy.DESTROY
    
    def _get_billing_mode(self) -> dynamodb.BillingMode:
        """Get billing mode for production environment"""
        # Production environment uses provisioned capacity with auto-scaling
        return dynamodb.BillingMode.PROVISIONED
    
    def _get_table_capacity_config(self) -> Dict[str, int]:
        """Get table capacity configuration for production environment"""
        # Production baseline capacity with auto-scaling
        return {
            "read_capacity": 5,
            "write_capacity": 5
        }
    
    def _get_point_in_time_recovery(self) -> bool:
        """Get point-in-time recovery setting for production environment"""
        # Disable PITR to allow proper rollback/deletion during deployment failures
        # In production, consider enabling this only after stable deployment
        return False
    
    def _get_encryption_config(self) -> Dict[str, Any]:
        """Get encryption configuration based on available KMS key"""
        if self.kms_key:
            # Use customer-managed KMS key if provided
            return {
                "encryption": dynamodb.TableEncryption.CUSTOMER_MANAGED,
                "encryption_key": self.kms_key
            }
        else:
            # Default to AWS-managed encryption (SSE)
            return {
                "encryption": dynamodb.TableEncryption.AWS_MANAGED
            }
    
    def _create_user_budget_table(self) -> None:
        """Create the user budget tracking table"""
        # Get encryption configuration
        encryption_props = self._get_encryption_config()
        
        capacity_config = self._get_table_capacity_config()
        
        table_props = {
            "table_name": f"bedrock-budgeteer-{self.environment_name}-user-budgets",
            "partition_key": dynamodb.Attribute(
                name="principal_id",
                type=dynamodb.AttributeType.STRING
            ),
            "billing_mode": self.billing_mode,
            "removal_policy": self.removal_policy,
            "point_in_time_recovery_specification": dynamodb.PointInTimeRecoverySpecification(
                point_in_time_recovery_enabled=self._get_point_in_time_recovery()
            ),
            **encryption_props
        }
        
        # Add provisioned throughput for production environment
        if self.billing_mode == dynamodb.BillingMode.PROVISIONED:
            table_props.update({
                "read_capacity": capacity_config["read_capacity"],
                "write_capacity": capacity_config["write_capacity"]
            })
        
        self.tables["user_budgets"] = dynamodb.Table(
            self, "UserBudgetTable",
            **table_props
        )
        
        # Add auto-scaling
        self._add_auto_scaling(self.tables["user_budgets"], "user_budgets")
        
        # Add Global Secondary Index for budget status queries
        gsi_props = {
            "index_name": "BudgetStatusIndex",
            "partition_key": dynamodb.Attribute(
                name="budget_status",
                type=dynamodb.AttributeType.STRING
            ),
            "sort_key": dynamodb.Attribute(
                name="created_at",
                type=dynamodb.AttributeType.STRING
            )
        }
        
        # Add GSI capacity for provisioned mode
        if self.billing_mode == dynamodb.BillingMode.PROVISIONED:
            gsi_props.update({
                "read_capacity": capacity_config["read_capacity"],
                "write_capacity": capacity_config["write_capacity"]
            })
        
        self.tables["user_budgets"].add_global_secondary_index(**gsi_props)
    
    def _create_usage_tracking_table(self) -> None:
        """Create the usage tracking table for AWS service consumption"""
        # Get encryption configuration
        encryption_props = self._get_encryption_config()
        
        capacity_config = self._get_table_capacity_config()
        
        table_props = {
            "table_name": f"bedrock-budgeteer-{self.environment_name}-usage-tracking",
            "partition_key": dynamodb.Attribute(
                name="principal_id",
                type=dynamodb.AttributeType.STRING
            ),
            "sort_key": dynamodb.Attribute(
                name="timestamp",
                type=dynamodb.AttributeType.STRING
            ),
            "billing_mode": self.billing_mode,
            "removal_policy": self.removal_policy,
            "point_in_time_recovery_specification": dynamodb.PointInTimeRecoverySpecification(
                point_in_time_recovery_enabled=self._get_point_in_time_recovery()
            ),
            **encryption_props
        }
        
        if self.billing_mode == dynamodb.BillingMode.PROVISIONED:
            table_props.update({
                "read_capacity": max(capacity_config["read_capacity"], 10),
                "write_capacity": max(capacity_config["write_capacity"], 20)  # Higher write capacity for usage events
            })
        
        self.tables["usage_tracking"] = dynamodb.Table(
            self, "UsageTrackingTable", 
            **table_props
        )
        
        # Add auto-scaling
        self._add_auto_scaling(self.tables["usage_tracking"], "usage_tracking")
        
        # Add GSI for service-based queries
        gsi_props = {
            "index_name": "ServiceUsageIndex",
            "partition_key": dynamodb.Attribute(
                name="service_name",
                type=dynamodb.AttributeType.STRING
            ),
            "sort_key": dynamodb.Attribute(
                name="timestamp",
                type=dynamodb.AttributeType.STRING
            )
        }
        
        # Add GSI capacity for provisioned mode
        if self.billing_mode == dynamodb.BillingMode.PROVISIONED:
            gsi_props.update({
                "read_capacity": max(capacity_config["read_capacity"], 10),
                "write_capacity": max(capacity_config["write_capacity"], 20)
            })
        
        self.tables["usage_tracking"].add_global_secondary_index(**gsi_props)
    

    

    
    def _add_auto_scaling(self, table: dynamodb.Table, table_type: str) -> None:
        """Add auto-scaling configuration for production DynamoDB tables"""
        
        # Auto-scaling configuration based on table type
        scaling_configs = {
            "user_budgets": {"min_read": 5, "max_read": 40, "min_write": 5, "max_write": 40},
            "usage_tracking": {"min_read": 10, "max_read": 100, "min_write": 20, "max_write": 200},
            "audit_logs": {"min_read": 10, "max_read": 100, "min_write": 25, "max_write": 250}
        }
        
        config = scaling_configs.get(table_type, scaling_configs["user_budgets"])
        
        # Read capacity auto-scaling
        read_scaling = table.auto_scale_read_capacity(
            min_capacity=config["min_read"],
            max_capacity=config["max_read"]
        )
        
        read_scaling.scale_on_utilization(
            target_utilization_percent=70,
            scale_in_cooldown=Duration.seconds(60),
            scale_out_cooldown=Duration.seconds(60)
        )
        
        # Write capacity auto-scaling
        write_scaling = table.auto_scale_write_capacity(
            min_capacity=config["min_write"],
            max_capacity=config["max_write"]
        )
        
        write_scaling.scale_on_utilization(
            target_utilization_percent=70,
            scale_in_cooldown=Duration.seconds(60),
            scale_out_cooldown=Duration.seconds(60)
        )
    
    def _create_audit_logs_table(self) -> None:
        """Create the audit logs table for CloudTrail event tracking"""
        # Get encryption configuration
        encryption_props = self._get_encryption_config()
        
        capacity_config = self._get_table_capacity_config()
        
        table_props = {
            "table_name": f"bedrock-budgeteer-{self.environment_name}-audit-logs",
            "partition_key": dynamodb.Attribute(
                name="event_id",
                type=dynamodb.AttributeType.STRING
            ),
            "sort_key": dynamodb.Attribute(
                name="event_time",
                type=dynamodb.AttributeType.STRING
            ),
            "billing_mode": self.billing_mode,
            "removal_policy": self.removal_policy,
            "point_in_time_recovery_specification": dynamodb.PointInTimeRecoverySpecification(
                point_in_time_recovery_enabled=self._get_point_in_time_recovery()
            ),
            **encryption_props
        }
        
        if self.billing_mode == dynamodb.BillingMode.PROVISIONED:
            table_props.update({
                "read_capacity": max(capacity_config["read_capacity"], 10),
                "write_capacity": max(capacity_config["write_capacity"], 25)  # High write capacity for audit events
            })
        
        self.tables["audit_logs"] = dynamodb.Table(
            self, "AuditLogsTable",
            **table_props
        )
        
        # Add auto-scaling
        self._add_auto_scaling(self.tables["audit_logs"], "audit_logs")
        
        # Add GSI for user-based audit queries
        gsi_props = {
            "index_name": "UserAuditIndex",
            "partition_key": dynamodb.Attribute(
                name="user_identity",
                type=dynamodb.AttributeType.STRING
            ),
            "sort_key": dynamodb.Attribute(
                name="event_time",
                type=dynamodb.AttributeType.STRING
            )
        }
        
        # Add GSI capacity for provisioned mode
        if self.billing_mode == dynamodb.BillingMode.PROVISIONED:
            gsi_props.update({
                "read_capacity": max(capacity_config["read_capacity"], 10),
                "write_capacity": max(capacity_config["write_capacity"], 25)
            })
        
        self.tables["audit_logs"].add_global_secondary_index(**gsi_props)
        
        # Add GSI for event source based queries (e.g., all Bedrock events)
        gsi2_props = {
            "index_name": "EventSourceIndex",
            "partition_key": dynamodb.Attribute(
                name="event_source",
                type=dynamodb.AttributeType.STRING
            ),
            "sort_key": dynamodb.Attribute(
                name="event_time",
                type=dynamodb.AttributeType.STRING
            )
        }
        
        if self.billing_mode == dynamodb.BillingMode.PROVISIONED:
            gsi2_props.update({
                "read_capacity": max(capacity_config["read_capacity"], 5),
                "write_capacity": max(capacity_config["write_capacity"], 10)
            })
        
        self.tables["audit_logs"].add_global_secondary_index(**gsi2_props)
    
    def _create_pricing_table(self) -> None:
        """Create pricing table for storing AWS Bedrock model pricing data"""
        
        capacity_config = self._get_table_capacity_config()
        
        table_props = {
            "table_name": f"bedrock-budgeteer-{self.environment_name}-pricing",
            "partition_key": dynamodb.Attribute(
                name="model_id",
                type=dynamodb.AttributeType.STRING
            ),
            "sort_key": dynamodb.Attribute(
                name="region",
                type=dynamodb.AttributeType.STRING
            ),
            "billing_mode": self.billing_mode,
            "removal_policy": self.removal_policy,
            "point_in_time_recovery_specification": dynamodb.PointInTimeRecoverySpecification(
                point_in_time_recovery_enabled=self._get_point_in_time_recovery()
            ),
            "time_to_live_attribute": "ttl"
        }
        
        # Add encryption
        if self.kms_key:
            table_props["encryption"] = dynamodb.TableEncryption.CUSTOMER_MANAGED
            table_props["encryption_key"] = self.kms_key
        else:
            table_props["encryption"] = dynamodb.TableEncryption.AWS_MANAGED
        
        # Add provisioned capacity if needed
        if self.billing_mode == dynamodb.BillingMode.PROVISIONED:
            table_props.update({
                "read_capacity": max(capacity_config["read_capacity"], 5),  # Low read capacity - infrequent access
                "write_capacity": max(capacity_config["write_capacity"], 2)  # Very low write capacity - daily updates
            })
        
        self.tables["pricing"] = dynamodb.Table(
            self, "PricingTable",
            **table_props
        )
        
        # Add auto-scaling for production
        self._add_auto_scaling(self.tables["pricing"], "pricing")
        
        # TTL for pricing cache expiration is configured in table_props above
