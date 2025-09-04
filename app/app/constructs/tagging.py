"""
Tagging Framework for Bedrock Budgeteer
Implements consistent tagging using CDK Aspects and Tags
"""
from typing import Dict, Optional
import jsii
from aws_cdk import (
    IAspect,
    CfnResource,
)
from constructs import Construct, IConstruct


@jsii.implements(IAspect)
class UnifiedTaggingAspect:
    """Unified CDK Aspect that applies all tags (core, compliance, and cost optimization) to avoid conflicts"""
    
    def __init__(self, environment_name: str, additional_tags: Optional[Dict[str, str]] = None):
        self.environment_name = environment_name
        
        # Core required tags for all resources
        self.required_tags = {
            "App": "bedrock-budgeteer",
            "Owner": "devops@company1.com",
            "Project": "cost-management",
            "CostCenter": "engineering-ops", 
            "BillingProject": "bedrock-budget-control",
            "Environment": environment_name,
            "ManagedBy": "cdk",
            "Version": "v1.0.0"
        }
        
        # Cost optimization tags for production environment
        self.cost_tags = {
            "AutoShutdown": "disabled",
            "CostOptimization": "conservative",
            "ResourceTTL": "permanent"
        }
        
        # Compliance requirements by resource type
        self.compliance_tags = {
            "AWS::DynamoDB::Table": {
                "BackupRequired": "true"
            },
            "AWS::Lambda::Function": {
                "DataClassification": "internal" 
            },
            "AWS::StepFunctions::StateMachine": {
                "DataClassification": "internal",
                "AuditTrail": "enabled"
            },
            "AWS::Events::Rule": {
                "MonitoringLevel": "standard"
            },
            "AWS::KMS::Key": {
                "KeyRotation": "enabled"
            },
            "AWS::Logs::LogGroup": {
                "DataClassification": "internal",
            },
            "AWS::SNS::Topic": {
                "DataClassification": "internal",
                "NotificationLevel": "operational"
            }
        }
        
        if additional_tags:
            self.required_tags.update(additional_tags)
    
    def visit(self, node: IConstruct) -> None:
        """Visit each construct and apply all tags in one pass"""
        # Only apply tags to CloudFormation resources to avoid infinite loops
        # Tags.of().add() creates new Aspects which can trigger this Aspect again
        if isinstance(node, CfnResource):
            # Collect all tags to apply
            all_tags = {}
            
            # Add core required tags
            all_tags.update(self.required_tags)
            
            # Add cost optimization tags
            all_tags.update(self.cost_tags)
            
            # Add compliance tags based on resource type
            resource_type = node.cfn_resource_type
            if resource_type in self.compliance_tags:
                all_tags.update(self.compliance_tags[resource_type])
            
            # Apply tags only at CloudFormation level to avoid creating new Aspects
            self._apply_cfn_tags(node, all_tags)
    
    def _apply_cfn_tags(self, cfn_resource: CfnResource, tags: Dict[str, str]) -> None:
        """Apply tags at the CloudFormation resource level"""
        try:
            # Most AWS resources support tags through the tags property
            if hasattr(cfn_resource, "tags") and cfn_resource.tags is not None:
                for tag_key, tag_value in tags.items():
                    cfn_resource.tags.set_tag(tag_key, tag_value)
            
            # Some resources use different tag properties
            elif hasattr(cfn_resource, "tag_specifications"):
                # Resources like EC2 instances use tag_specifications
                tag_list = [{"key": k, "value": v} for k, v in tags.items()]
                if not cfn_resource.tag_specifications:
                    cfn_resource.tag_specifications = []
                cfn_resource.tag_specifications.extend(tag_list)
            
            # For resources that don't support tags, we skip silently
            # This prevents errors on resources like IAM policies that don't support tags
            
        except Exception:
            # If tagging fails for any reason, continue without breaking the synthesis
            # This ensures that unsupported resources don't break the entire deployment
            pass





class TaggingFramework(Construct):
    """Centralized tagging framework that applies all tagging aspects"""
    
    def __init__(self, scope: Construct, construct_id: str, 
                 environment_name: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)
        
        self.environment_name = environment_name
        
        # Apply all tagging aspects to the scope
        self._apply_tagging_aspects(scope)
    
    def _apply_tagging_aspects(self, scope: Construct) -> None:
        """Apply unified tagging aspect to the given scope"""
        from aws_cdk import Aspects, AspectPriority
        
        # Single unified tagging aspect - applies all tags (core, compliance, cost) in one pass
        # Set to MUTATING priority (200) to match Tags.of().add() calls and avoid priority conflicts
        Aspects.of(scope).add(
            UnifiedTaggingAspect(self.environment_name),
            priority=AspectPriority.MUTATING
        )

