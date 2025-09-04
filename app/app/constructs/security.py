"""
Security Construct for Bedrock Budgeteer
Manages IAM roles, policies, and security-related resources
"""
from typing import Dict, List, Any
from aws_cdk import (
    aws_iam as iam,
)
from constructs import Construct


class SecurityConstruct(Construct):
    """Construct for IAM roles, policies, and security resources"""
    
    def __init__(self, scope: Construct, construct_id: str, 
                 environment_name: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)
        
        self.environment_name = environment_name
        self.roles: Dict[str, iam.Role] = {}
        self.policies: Dict[str, iam.ManagedPolicy] = {}
        
        # Create service roles
        self._create_lambda_execution_role()
        self._create_step_functions_role()
        self._create_eventbridge_role()
        self._create_bedrock_logging_role()
        
        # Create custom policies
        self._create_dynamodb_access_policy()
        self._create_eventbridge_publish_policy()
        
        # Tags are applied by TaggingFramework aspects
    
    def _create_lambda_execution_role(self) -> None:
        """Create IAM role for Lambda functions"""
        self.roles["lambda_execution"] = iam.Role(
            self, "LambdaExecutionRole",
            role_name=f"bedrock-budgeteer-{self.environment_name}-lambda-execution",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            description="Execution role for Bedrock Budgeteer Lambda functions",
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AWSLambdaBasicExecutionRole"
                )
            ]
        )
        
        # Add CloudWatch Logs permissions
        self.roles["lambda_execution"].add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "logs:CreateLogGroup",
                    "logs:CreateLogStream", 
                    "logs:PutLogEvents"
                ],
                resources=[
                    f"arn:aws:logs:*:*:log-group:/aws/lambda/bedrock-budgeteer-{self.environment_name}-*"
                ]
            )
        )
    
    def _create_step_functions_role(self) -> None:
        """Create IAM role for Step Functions"""
        self.roles["step_functions"] = iam.Role(
            self, "StepFunctionsRole",
            role_name=f"bedrock-budgeteer-{self.environment_name}-step-functions",
            assumed_by=iam.ServicePrincipal("states.amazonaws.com"),
            description="Execution role for Bedrock Budgeteer Step Functions"
        )
        
        # Add CloudWatch Logs permissions for Step Functions
        self.roles["step_functions"].add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "logs:CreateLogDelivery",
                    "logs:CreateLogGroup",
                    "logs:CreateLogStream",
                    "logs:PutLogEvents",
                    "logs:DeleteLogDelivery",
                    "logs:DescribeLogGroups",
                    "logs:DescribeResourcePolicies",
                    "logs:GetLogDelivery",
                    "logs:ListLogDeliveries",
                    "logs:PutResourcePolicy",
                    "logs:UpdateLogDelivery"
                ],
                resources=["*"]
            )
        )
    
    def _create_eventbridge_role(self) -> None:
        """Create IAM role for EventBridge"""
        self.roles["eventbridge"] = iam.Role(
            self, "EventBridgeRole", 
            role_name=f"bedrock-budgeteer-{self.environment_name}-eventbridge",
            assumed_by=iam.ServicePrincipal("events.amazonaws.com"),
            description="Service role for Bedrock Budgeteer EventBridge"
        )
    
    def _create_bedrock_logging_role(self) -> None:
        """Create IAM role for Bedrock invocation logging to CloudWatch"""
        self.roles["bedrock_logging"] = iam.Role(
            self, "BedrockLoggingRole",
            role_name=f"bedrock-budgeteer-{self.environment_name}-bedrock-logging",
            assumed_by=iam.ServicePrincipal("bedrock.amazonaws.com"),
            description="Role for Bedrock to write invocation logs to CloudWatch",
            inline_policies={
                "BedrockLoggingPolicy": iam.PolicyDocument(
                    statements=[
                        iam.PolicyStatement(
                            effect=iam.Effect.ALLOW,
                            actions=[
                                "logs:CreateLogGroup",
                                "logs:CreateLogStream",
                                "logs:PutLogEvents"
                            ],
                            resources=[
                                f"arn:aws:logs:*:*:log-group:/aws/bedrock/bedrock-budgeteer-{self.environment_name}-invocation-logs*"
                            ]
                        )
                    ]
                )
            }
        )
    
    def _create_dynamodb_access_policy(self) -> None:
        """Create managed policy for DynamoDB access"""
        self.policies["dynamodb_access"] = iam.ManagedPolicy(
            self, "DynamoDBAccessPolicy",
            managed_policy_name=f"bedrock-budgeteer-{self.environment_name}-dynamodb-access",
            description="Policy for DynamoDB access with least privilege",
            statements=[
                iam.PolicyStatement(
                    effect=iam.Effect.ALLOW,
                    actions=[
                        "dynamodb:GetItem",
                        "dynamodb:PutItem", 
                        "dynamodb:UpdateItem",
                        "dynamodb:DeleteItem",
                        "dynamodb:Query",
                        "dynamodb:Scan"
                    ],
                    resources=[
                        f"arn:aws:dynamodb:*:*:table/bedrock-budgeteer-{self.environment_name}-*",
                        f"arn:aws:dynamodb:*:*:table/bedrock-budgeteer-{self.environment_name}-*/index/*"
                    ]
                ),
                iam.PolicyStatement(
                    effect=iam.Effect.ALLOW,
                    actions=[
                        "dynamodb:BatchGetItem",
                        "dynamodb:BatchWriteItem"
                    ],
                    resources=[
                        f"arn:aws:dynamodb:*:*:table/bedrock-budgeteer-{self.environment_name}-*"
                    ]
                )
            ]
        )
        
        # Attach to Lambda execution role
        self.roles["lambda_execution"].add_managed_policy(
            self.policies["dynamodb_access"]
        )
    
    def _create_eventbridge_publish_policy(self) -> None:
        """Create managed policy for EventBridge publishing"""
        self.policies["eventbridge_publish"] = iam.ManagedPolicy(
            self, "EventBridgePublishPolicy",
            managed_policy_name=f"bedrock-budgeteer-{self.environment_name}-eventbridge-publish",
            description="Policy for publishing events to EventBridge",
            statements=[
                iam.PolicyStatement(
                    effect=iam.Effect.ALLOW,
                    actions=[
                        "events:PutEvents"
                    ],
                    resources=[
                        f"arn:aws:events:*:*:event-bus/bedrock-budgeteer-{self.environment_name}-*",
                        "arn:aws:events:*:*:event-bus/default"
                    ]
                )
            ]
        )
        
        # Attach to Lambda execution role
        self.roles["lambda_execution"].add_managed_policy(
            self.policies["eventbridge_publish"]
        )
    
    def create_policy_template(self, service_name: str, actions: List[str], 
                              resources: List[str]) -> iam.ManagedPolicy:
        """Create a reusable policy template for any AWS service"""
        return iam.ManagedPolicy(
            self, f"{service_name.title()}Policy",
            managed_policy_name=f"bedrock-budgeteer-{self.environment_name}-{service_name}",
            description=f"Least-privilege policy for {service_name} access",
            statements=[
                iam.PolicyStatement(
                    effect=iam.Effect.ALLOW,
                    actions=actions,
                    resources=resources
                )
            ]
        )
    
    def create_lambda_policy_template(self, function_name: str, 
                                    additional_permissions: List[Dict[str, any]] = None) -> iam.ManagedPolicy:
        """Create a policy template specifically for Lambda functions"""
        statements = [
            # Basic Lambda execution permissions
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "logs:CreateLogGroup",
                    "logs:CreateLogStream",
                    "logs:PutLogEvents"
                ],
                resources=[
                    f"arn:aws:logs:*:*:log-group:/aws/lambda/bedrock-budgeteer-{self.environment_name}-{function_name}",
                    f"arn:aws:logs:*:*:log-group:/aws/lambda/bedrock-budgeteer-{self.environment_name}-{function_name}:*"
                ]
            )
        ]
        
        # Add additional permissions if provided
        if additional_permissions:
            for perm in additional_permissions:
                statements.append(
                    iam.PolicyStatement(
                        effect=iam.Effect.ALLOW,
                        actions=perm.get("actions", []),
                        resources=perm.get("resources", ["*"]),
                        conditions=perm.get("conditions", None)
                    )
                )
        
        return iam.ManagedPolicy(
            self, f"{function_name.title()}LambdaPolicy",
            managed_policy_name=f"bedrock-budgeteer-{self.environment_name}-lambda-{function_name}",
            description=f"Least-privilege policy for {function_name} Lambda function",
            statements=statements
        )
    
    def create_kms_access_policy(self, key_arn: str, actions: List[str] = None) -> iam.ManagedPolicy:
        """Create a policy template for KMS key access"""
        if actions is None:
            actions = [
                "kms:Encrypt",
                "kms:Decrypt", 
                "kms:ReEncrypt*",
                "kms:GenerateDataKey*",
                "kms:DescribeKey"
            ]
        
        return iam.ManagedPolicy(
            self, "KMSAccessPolicy",
            managed_policy_name=f"bedrock-budgeteer-{self.environment_name}-kms-access",
            description="Policy for KMS key access",
            statements=[
                iam.PolicyStatement(
                    effect=iam.Effect.ALLOW,
                    actions=actions,
                    resources=[key_arn]
                )
            ]
        )
    
    def add_lambda_invoke_permissions(self, function_arns: List[str]) -> None:
        """Add Lambda invoke permissions to Step Functions role"""
        if function_arns:
            self.roles["step_functions"].add_to_policy(
                iam.PolicyStatement(
                    effect=iam.Effect.ALLOW,
                    actions=["lambda:InvokeFunction"],
                    resources=function_arns
                )
            )
    
    def add_bedrock_permissions(self) -> None:
        """Add Bedrock API permissions for cost monitoring"""
        bedrock_policy = iam.PolicyStatement(
            effect=iam.Effect.ALLOW,
            actions=[
                "bedrock:GetFoundationModel",
                "bedrock:ListFoundationModels",
                "bedrock:GetModelInvocationLoggingConfiguration",
                "bedrock:InvokeModel",
                "bedrock:InvokeModelWithResponseStream"
            ],
            resources=["*"]  # Bedrock requires wildcard for these actions
        )
        
        self.roles["lambda_execution"].add_to_policy(bedrock_policy)
    
    def add_pricing_api_permissions(self) -> None:
        """Add AWS Pricing API permissions for cost calculation"""
        pricing_policy = iam.PolicyStatement(
            effect=iam.Effect.ALLOW,
            actions=[
                "pricing:GetProducts",
                "pricing:DescribeServices",
                "pricing:GetAttributeValues"
            ],
            resources=["*"]  # Pricing API requires wildcard
        )
        
        self.roles["lambda_execution"].add_to_policy(pricing_policy)
    
    def add_cloudtrail_permissions(self) -> None:
        """Add CloudTrail permissions for usage tracking"""
        cloudtrail_policy = iam.PolicyStatement(
            effect=iam.Effect.ALLOW,
            actions=[
                "cloudtrail:LookupEvents"
            ],
            resources=["*"]
        )
        
        self.roles["lambda_execution"].add_to_policy(cloudtrail_policy)
    
    def add_ssm_permissions(self) -> None:
        """Add SSM Parameter Store permissions for configuration access"""
        ssm_policy = iam.PolicyStatement(
            effect=iam.Effect.ALLOW,
            actions=[
                "ssm:GetParameter",
                "ssm:GetParameters",
                "ssm:GetParametersByPath"
            ],
            resources=[f"arn:aws:ssm:*:*:parameter/bedrock-budgeteer/*"]
        )
        
        self.roles["lambda_execution"].add_to_policy(ssm_policy)
    
    def add_iam_read_permissions(self) -> None:
        """Add IAM read permissions for policy management"""
        iam_read_policy = iam.PolicyStatement(
            effect=iam.Effect.ALLOW,
            actions=[
                "iam:GetUser",
                "iam:GetRole", 
                "iam:ListAttachedUserPolicies",
                "iam:ListAttachedRolePolicies",
                "iam:GetUserPolicy",
                "iam:GetRolePolicy"
            ],
            resources=["*"]
        )
        
        self.roles["lambda_execution"].add_to_policy(iam_read_policy)
    
    def add_cloudwatch_metrics_permissions(self) -> None:
        """Add CloudWatch custom metrics permissions"""
        cloudwatch_policy = iam.PolicyStatement(
            effect=iam.Effect.ALLOW,
            actions=[
                "cloudwatch:PutMetricData"
            ],
            resources=["*"]
        )
        
        self.roles["lambda_execution"].add_to_policy(cloudwatch_policy)
    
    def add_dynamodb_permissions(self, tables: Dict[str, Any]) -> None:
        """Add DynamoDB permissions for Lambda functions"""
        for table_name, table in tables.items():
            table.grant_read_write_data(self.roles["lambda_execution"])
    
    def add_s3_permissions(self, bucket: Any) -> None:
        """Add S3 permissions for Lambda functions"""
        bucket.grant_read(self.roles["lambda_execution"])
    
    def add_sqs_permissions(self, queues: Dict[str, Any]) -> None:
        """Add SQS permissions for DLQ access"""
        for queue in queues.values():
            queue.grant_send_messages(self.roles["lambda_execution"])
    
    # Public properties to expose resources
    @property
    def bedrock_logging_role(self) -> iam.Role:
        """Get the Bedrock logging role for invocation logging configuration"""
        return self.roles["bedrock_logging"]
    
    @property
    def lambda_execution_role(self) -> iam.Role:
        """Get the Lambda execution role for additional permissions"""
        return self.roles["lambda_execution"]

