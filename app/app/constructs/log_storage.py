"""
Log Storage Construct for Bedrock Budgeteer
Manages S3 buckets for log storage with lifecycle policies and security settings
"""
from typing import Dict, Optional, List
from aws_cdk import (
    aws_s3 as s3,
    aws_iam as iam,
    aws_kms as kms,
    RemovalPolicy,
    Duration,
)
from constructs import Construct


class LogStorageConstruct(Construct):
    """Construct for S3-based log storage with lifecycle management"""
    
    def __init__(self, scope: Construct, construct_id: str, 
                 environment_name: str,
                 kms_key: Optional[kms.IKey] = None,
                 **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)
        
        self.environment_name = environment_name
        self.kms_key = kms_key
        
        # Initialize storage for created resources
        self.buckets: Dict[str, s3.Bucket] = {}
        
        # Environment-specific configurations
        self.removal_policy = self._get_removal_policy()
        self.versioning_enabled = self._get_versioning_setting()
        self.encryption_type = self._get_encryption_type()
        
        # Create S3 bucket for log storage
        self._create_logs_bucket()
        
        # Configure bucket policies
        self._configure_bucket_policies()
        
        # Tags are applied by TaggingFramework aspects
    
    def _should_skip_public_access_block(self) -> bool:
        """Check if S3 public access block should be skipped (for enterprise SCPs)"""
        try:
            return self.node.try_get_context("bedrock-budgeteer:feature-flags").get("skip-s3-public-access-block", False)
        except (AttributeError, TypeError):
            return False
    
    def _get_removal_policy(self) -> RemovalPolicy:
        """Get removal policy for production environment"""
        # Allow resource deletion for proper rollback during deployment failures
        return RemovalPolicy.DESTROY
    
    def _get_versioning_setting(self) -> bool:
        """Get versioning setting for production environment"""
        # Disable versioning to allow proper bucket deletion during rollback
        return False
    
    def _get_encryption_type(self) -> s3.BucketEncryption:
        """Get encryption type for production environment"""
        # Production environment uses KMS encryption if key is available, otherwise S3-managed
        if self.kms_key:
            return s3.BucketEncryption.KMS
        else:
            return s3.BucketEncryption.S3_MANAGED
    
    def _create_logs_bucket(self) -> None:
        """Create the main logs bucket for active log storage"""
        
        # Define lifecycle rules - delete files older than 30 days
        lifecycle_rules = self._get_lifecycle_rules()
        
        encryption_props = {}
        if self.encryption_type == s3.BucketEncryption.KMS and self.kms_key:
            encryption_props = {
                "encryption": s3.BucketEncryption.KMS,
                "encryption_key": self.kms_key
            }
        else:
            encryption_props = {
                "encryption": s3.BucketEncryption.S3_MANAGED
            }
        


        logs_bucket_props = {
            "bucket_name": f"bedrock-budgeteer-{self.environment_name}-logs",
            "removal_policy": self.removal_policy,
            "versioned": self.versioning_enabled,
            "lifecycle_rules": lifecycle_rules,
            "public_read_access": False,
            "auto_delete_objects": True,  # Allow CDK to delete objects during bucket deletion
            "object_ownership": s3.ObjectOwnership.BUCKET_OWNER_PREFERRED,  # Allow ACLs for CloudTrail
            **encryption_props
        }
        
        # Only add public access block if not skipped (for enterprise SCPs)
        if not self._should_skip_public_access_block():
            logs_bucket_props["block_public_access"] = s3.BlockPublicAccess.BLOCK_ACLS
            
        self.buckets["logs"] = s3.Bucket(self, "LogsBucket", **logs_bucket_props)
    
    def _get_lifecycle_rules(self) -> List[s3.LifecycleRule]:
        """Get lifecycle rules for logs bucket - delete files older than 30 days"""
        return [
            s3.LifecycleRule(
                id="LogsLifecycle",
                enabled=True,
                expiration=Duration.days(30),  # Delete files older than 30 days
                abort_incomplete_multipart_upload_after=Duration.days(1)
            )
        ]
    
    def _configure_bucket_policies(self) -> None:
        """Configure bucket policies for secure access"""
        
        # Note: CloudTrail bucket policies are automatically managed by the CloudTrail construct
        # when the trail is created. No manual bucket policy configuration needed here.
        pass
    
    def add_bucket_notification(self, bucket_name: str, notification, 
                               filters: List[s3.NotificationKeyFilter] = None) -> None:
        """Add notification configuration to a bucket"""
        if bucket_name in self.buckets:
            if filters:
                for filter_config in filters:
                    self.buckets[bucket_name].add_object_created_notification(
                        notification, 
                        filter_config
                    )
            else:
                self.buckets[bucket_name].add_object_created_notification(notification)
        else:
            raise ValueError(f"Bucket '{bucket_name}' not found")
    
    def grant_read_access(self, bucket_name: str, grantee: iam.IGrantable, 
                         object_key_prefix: str = "*") -> iam.Grant:
        """Grant read access to a specific bucket and path"""
        if bucket_name in self.buckets:
            return self.buckets[bucket_name].grant_read(grantee, object_key_prefix)
        else:
            raise ValueError(f"Bucket '{bucket_name}' not found")
    
    def grant_write_access(self, bucket_name: str, grantee: iam.IGrantable, 
                          object_key_prefix: str = "*") -> iam.Grant:
        """Grant write access to a specific bucket and path"""
        if bucket_name in self.buckets:
            return self.buckets[bucket_name].grant_write(grantee, object_key_prefix)
        else:
            raise ValueError(f"Bucket '{bucket_name}' not found")
    

    
    @property
    def logs_bucket(self) -> s3.Bucket:
        """Get the main logs bucket"""
        return self.buckets["logs"]
    
    @property
    def logs_bucket_name(self) -> str:
        """Get the main logs bucket name"""
        return self.buckets["logs"].bucket_name
