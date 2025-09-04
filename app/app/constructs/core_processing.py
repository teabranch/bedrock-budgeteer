"""
Core Processing Construct - Refactored
Implements Lambda functions for processing events, calculating costs, and monitoring budgets
"""
from typing import Dict, Any, Optional
from aws_cdk import (
    Duration,
    RemovalPolicy,
    aws_lambda as lambda_,
    aws_iam as iam,
    aws_dynamodb as dynamodb,
    aws_s3 as s3,
    aws_events as events,
    aws_events_targets as targets,
    aws_sqs as sqs,
    aws_kms as kms,
)
from constructs import Construct

# Import shared utilities and Lambda function implementations
from .shared.lambda_utilities import get_shared_lambda_utilities
from .lambda_functions.user_setup import get_user_setup_function_code
from .lambda_functions.usage_calculator import get_usage_calculator_function_code


class CoreProcessingConstruct(Construct):
    """Core processing logic for Bedrock cost monitoring and budget enforcement"""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        environment_name: str,
        dynamodb_tables: Dict[str, dynamodb.Table],
        s3_bucket: s3.Bucket,
        lambda_execution_role: iam.Role,
        kms_key: Optional[kms.Key] = None,
        **kwargs
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)
        
        self.environment_name = environment_name
        self.dynamodb_tables = dynamodb_tables
        self.s3_bucket = s3_bucket
        self.lambda_execution_role = lambda_execution_role
        self.kms_key = kms_key
        
        # Storage for created Lambda functions
        self.lambda_functions: Dict[str, lambda_.Function] = {}
        self.dlq_queues: Dict[str, sqs.Queue] = {}
        
        # Create shared resources
        self._create_shared_resources()
        
        # Create Lambda functions
        self._create_lambda_functions()
        
        # Set up event routing
        self._setup_event_routing()
        
        # Create monitoring schedule
        self._create_monitoring_schedule()
    
    def _create_shared_resources(self) -> None:
        """Create shared resources used by multiple Lambda functions"""
        
        # Create dead letter queues for error handling
        self._create_dead_letter_queues()
    
    def _create_dead_letter_queues(self) -> None:
        """Create dead letter queues for failed Lambda executions"""
        
        dlq_functions = [
            "user_setup",
            "usage_calculator", 
            "budget_monitor",
            "budget_refresh",
            "audit_logger",
            "state_reconciliation"
        ]
        
        for function_name in dlq_functions:
            dlq_name = f"bedrock-budgeteer-{function_name}-dlq-{self.environment_name}"
            
            self.dlq_queues[function_name] = sqs.Queue(
                self,
                f"{function_name.title().replace('_', '')}DLQ",
                queue_name=dlq_name,
                retention_period=Duration.days(14),
                visibility_timeout=Duration.minutes(5),
                encryption=sqs.QueueEncryption.KMS_MANAGED,
                removal_policy=RemovalPolicy.DESTROY
            )
    
    def _create_lambda_functions(self) -> None:
        """Create all core processing Lambda functions"""
        
        # Common Lambda configuration
        common_config = {
            "runtime": lambda_.Runtime.PYTHON_3_11,
            "timeout": Duration.minutes(5),
            "memory_size": 512,
            "role": self.lambda_execution_role,
            "environment": {
                "ENVIRONMENT": self.environment_name,
                "USER_BUDGETS_TABLE": self.dynamodb_tables["user_budgets"].table_name,
                "USAGE_TRACKING_TABLE": self.dynamodb_tables["usage_tracking"].table_name,
                "AUDIT_LOGS_TABLE": self.dynamodb_tables["audit_logs"].table_name,
                "PRICING_TABLE": self.dynamodb_tables["pricing"].table_name,
                "LOGS_BUCKET": self.s3_bucket.bucket_name
            }
        }
        
        # Create each Lambda function
        self._create_user_setup_lambda(common_config)
        self._create_usage_calculator_lambda(common_config)
        self._create_budget_monitor_lambda(common_config)
        self._create_budget_refresh_lambda(common_config)
        self._create_audit_logger_lambda(common_config)
        self._create_state_reconciliation_lambda(common_config)
        self._create_pricing_manager_lambda(common_config)
    
    def _create_user_setup_lambda(self, common_config: Dict[str, Any]) -> None:
        """Create Lambda function for user setup and budget initialization"""
        
        function_code = f"""
{get_shared_lambda_utilities()}

{get_user_setup_function_code()}
"""
        
        self.lambda_functions["user_setup"] = lambda_.Function(
            self,
            "UserSetupFunction",
            function_name=f"bedrock-budgeteer-user-setup-{self.environment_name}",
            code=lambda_.Code.from_inline(function_code),
            handler="index.lambda_handler",
            dead_letter_queue=self.dlq_queues["user_setup"],
            **common_config
        )
    
    def _create_usage_calculator_lambda(self, common_config: Dict[str, Any]) -> None:
        """Create Lambda function for usage cost calculation"""
        
        function_code = f"""
{get_shared_lambda_utilities()}

{get_usage_calculator_function_code()}
"""
        
        # Update memory and timeout for processing workload
        usage_config = common_config.copy()
        usage_config.update({
            "memory_size": 1024,
            "timeout": Duration.minutes(10)
        })
        
        self.lambda_functions["usage_calculator"] = lambda_.Function(
            self,
            "UsageCalculatorFunction", 
            function_name=f"bedrock-budgeteer-usage-calculator-{self.environment_name}",
            code=lambda_.Code.from_inline(function_code),
            handler="index.lambda_handler",
            dead_letter_queue=self.dlq_queues["usage_calculator"],
            **usage_config
        )
    
    def _create_budget_monitor_lambda(self, common_config: Dict[str, Any]) -> None:
        """Create Lambda function for budget monitoring and threshold evaluation"""
        
        function_code = f"""
{get_shared_lambda_utilities()}

def lambda_handler(event, context):
    \"\"\"Monitor budgets for threshold violations and trigger suspension workflows\"\"\"
    logger.info("Starting budget monitoring run")
    
    try:
        user_budgets_table = dynamodb.Table(os.environ['USER_BUDGETS_TABLE'])
        
        scan_kwargs = {{}}
        monitored_users = 0
        budget_exceeded_users = 0
        
        while True:
            response = user_budgets_table.scan(**scan_kwargs)
            
            for item in response['Items']:
                monitored_users += 1
                
                # Check for budget exceeded (100%+)
                principal_id = item['principal_id']
                spent_usd = float(item.get('spent_usd', 0))
                budget_limit_usd = float(item.get('budget_limit_usd', 0))
                status = item.get('status', 'active')
                grace_deadline_epoch = item.get('grace_deadline_epoch')
                
                # Skip if already suspended or not active
                if status in ['suspended', 'restricted'] or budget_limit_usd == 0:
                    continue
                
                # Check if budget is exceeded (100% or more)
                budget_usage_percent = (spent_usd / budget_limit_usd) * 100 if budget_limit_usd > 0 else 0
                
                if budget_usage_percent >= 100.0:
                    logger.warning(f"Budget exceeded for {{principal_id}}: ${{spent_usd:.2f}} / ${{budget_limit_usd:.2f}} ({{budget_usage_percent:.1f}}%)")
                    budget_exceeded_users += 1
                    
                    # Check if already in grace period
                    current_time = datetime.now(timezone.utc)
                    
                    if grace_deadline_epoch:
                        # Already in grace period - check if expired
                        # Convert Decimal to int/float for datetime.fromtimestamp()
                        try:
                            # Handle Decimal, int, float, or string epoch values
                            if hasattr(grace_deadline_epoch, '__float__'):
                                epoch_timestamp = float(grace_deadline_epoch)
                            else:
                                epoch_timestamp = float(str(grace_deadline_epoch))
                            grace_deadline = datetime.fromtimestamp(epoch_timestamp, timezone.utc)
                        except (ValueError, TypeError) as e:
                            logger.error(f"Invalid grace_deadline_epoch format for {{principal_id}}: {{grace_deadline_epoch}} - {{e}}")
                            # Skip this user if timestamp is invalid
                            continue
                        if current_time >= grace_deadline:
                            logger.error(f"Grace period expired for {{principal_id}} - triggering immediate suspension")
                            trigger_suspension_workflow(principal_id, item, "grace_period_expired")
                        else:
                            remaining_seconds = int((grace_deadline - current_time).total_seconds())
                            logger.info(f"{{principal_id}} still in grace period - {{remaining_seconds}}s remaining")
                    else:
                        # Budget just exceeded - start grace period
                        logger.error(f"Budget limit exceeded for {{principal_id}} - starting grace period")
                        start_grace_period(principal_id, item)
                
                # Also check for users approaching limits for early warning
                elif budget_usage_percent >= 90.0:
                    logger.warning(f"Budget critical threshold reached for {{principal_id}}: {{budget_usage_percent:.1f}}%")
            
            if 'LastEvaluatedKey' in response:
                scan_kwargs['ExclusiveStartKey'] = response['LastEvaluatedKey']
            else:
                break
        
        # Publish metrics
        MetricsPublisher.publish_budget_metric(
            'MonitoredUsers',
            monitored_users,
            'Count',
            {{'Environment': os.environ['ENVIRONMENT']}}
        )
        
        MetricsPublisher.publish_budget_metric(
            'BudgetExceededUsers',
            budget_exceeded_users,
            'Count',
            {{'Environment': os.environ['ENVIRONMENT']}}
        )
        
        logger.info(f"Budget monitoring completed: {{monitored_users}} users monitored, {{budget_exceeded_users}} budget exceeded")
        return {{
            'statusCode': 200,
            'monitored_users': monitored_users,
            'budget_exceeded_users': budget_exceeded_users
        }}
        
    except Exception as e:
        logger.error(f"Error in budget monitoring: {{e}}", exc_info=True)
        raise

def start_grace_period(principal_id, budget_item):
    \"\"\"Start grace period for budget exceeded user\"\"\"
    try:
        # Configurable grace period from SSM parameter
        grace_period_seconds = ConfigurationManager.get_parameter(
            '/bedrock-budgeteer/global/grace_period_seconds', 60
        )
        
        current_time = datetime.now(timezone.utc)
        grace_deadline = current_time + timedelta(seconds=grace_period_seconds)
        
        # Update budget record with grace deadline
        user_budgets_table = dynamodb.Table(os.environ['USER_BUDGETS_TABLE'])
        user_budgets_table.update_item(
            Key={{'principal_id': principal_id}},
            UpdateExpression='SET grace_deadline_epoch = :deadline, #status = :status',
            ExpressionAttributeNames={{'#status': 'status'}},
            ExpressionAttributeValues={{
                ':deadline': int(grace_deadline.timestamp()),
                ':status': 'grace_period'
            }}
        )
        
        # Publish grace period started event
        EventPublisher.publish_budget_event(
            'Grace Period Started',
            {{
                'principal_id': principal_id,
                'budget_limit_usd': float(budget_item.get('budget_limit_usd', 0)),
                'spent_usd': float(budget_item.get('spent_usd', 0)),
                'grace_period_seconds': grace_period_seconds,
                'grace_deadline': grace_deadline.isoformat(),
                'budget_usage_percent': (float(budget_item.get('spent_usd', 0)) / float(budget_item.get('budget_limit_usd', 1))) * 100
            }}
        )
        
        # Publish metric
        MetricsPublisher.publish_budget_metric(
            'GracePeriodsStarted',
            1.0,
            'Count',
            {{'Environment': os.environ['ENVIRONMENT'], 'PrincipalId': principal_id}}
        )
        
        logger.warning(f"Grace period started for {{principal_id}}: {{grace_period_seconds}}s until suspension")
        
    except Exception as e:
        logger.error(f"Error starting grace period for {{principal_id}}: {{e}}")
        # If grace period setup fails, trigger immediate suspension
        trigger_suspension_workflow(principal_id, budget_item, "grace_period_setup_failed")

def trigger_suspension_workflow(principal_id, budget_item, reason):
    \"\"\"Trigger suspension workflow via EventBridge\"\"\"
    try:
        # Get configurable grace period
        grace_period_seconds = ConfigurationManager.get_parameter(
            '/bedrock-budgeteer/global/grace_period_seconds', 60
        )
        
        # Publish suspension workflow trigger event
        EventPublisher.publish_budget_event(
            'Suspension Workflow Required',
            {{
                'principal_id': principal_id,
                'reason': reason,
                'grace_period_seconds': int(grace_period_seconds),
                'budget_data': {{
                    'account_type': budget_item.get('account_type', 'bedrock_api_key'),
                    'budget_limit_usd': float(budget_item.get('budget_limit_usd', 0)),
                    'spent_usd': float(budget_item.get('spent_usd', 0)),
                    'budget_usage_percent': (float(budget_item.get('spent_usd', 0)) / float(budget_item.get('budget_limit_usd', 1))) * 100
                }},
                'triggered_by': 'budget_monitor',
                'timestamp': datetime.now(timezone.utc).isoformat()
            }}
        )
        
        # Publish metric
        MetricsPublisher.publish_budget_metric(
            'SuspensionWorkflowsTriggered',
            1.0,
            'Count',
            {{'Environment': os.environ['ENVIRONMENT'], 'Reason': reason}}
        )
        
        logger.error(f"Suspension workflow triggered for {{principal_id}}: reason={{reason}}")
        
    except Exception as e:
        logger.error(f"Error triggering suspension workflow for {{principal_id}}: {{e}}")
        raise
"""
        
        self.lambda_functions["budget_monitor"] = lambda_.Function(
            self,
            "BudgetMonitorFunction",
            function_name=f"bedrock-budgeteer-budget-monitor-{self.environment_name}",
            code=lambda_.Code.from_inline(function_code),
            handler="index.lambda_handler",
            dead_letter_queue=self.dlq_queues["budget_monitor"],
            **common_config
        )
    
    def _create_budget_refresh_lambda(self, common_config: Dict[str, Any]) -> None:
        """Create Lambda function for budget refresh operations and automatic restoration"""
        
        function_code = f"""
{get_shared_lambda_utilities()}

def lambda_handler(event, context):
    \"\"\"Handle budget refresh operations and trigger automatic restoration for suspended users\"\"\"
    logger.info("Starting budget refresh and automatic restoration check")
    
    try:
        current_time = datetime.now(timezone.utc)
        user_budgets_table = dynamodb.Table(os.environ['USER_BUDGETS_TABLE'])
        
        refreshed_count = 0
        restoration_count = 0
        
        # Scan for users whose refresh period has been reached
        paginator = dynamodb_client.get_paginator('scan')
        page_iterator = paginator.paginate(TableName=os.environ['USER_BUDGETS_TABLE'])
        
        for page in page_iterator:
            for item in page.get('Items', []):
                principal_id = item.get('principal_id', {{}}).get('S', '')
                status = item.get('status', {{}}).get('S', 'active')
                refresh_date_str = item.get('budget_refresh_date', {{}}).get('S', '')
                
                if not principal_id or not refresh_date_str:
                    continue
                
                # Parse refresh date
                try:
                    refresh_date = datetime.fromisoformat(refresh_date_str.replace('Z', '+00:00'))
                except (ValueError, AttributeError):
                    logger.warning(f"Invalid refresh date format for {{principal_id}}: {{refresh_date_str}}")
                    continue
                
                # Check if refresh period has been reached
                if current_time >= refresh_date:
                    if status == 'suspended':
                        # Trigger automatic restoration workflow
                        try:
                            EventPublisher.publish_budget_event(
                                'Automatic User Restoration Required',
                                {{
                                    'principal_id': principal_id,
                                    'restoration_reason': 'budget_refresh_period_reached',
                                    'refresh_date': refresh_date.isoformat(),
                                    'current_time': current_time.isoformat()
                                }}
                            )
                            restoration_count += 1
                            logger.info(f"Triggered automatic restoration for suspended user: {{principal_id}}")
                        except Exception as e:
                            logger.error(f"Error triggering restoration for {{principal_id}}: {{e}}")
                    
                    elif status == 'active':
                        # Reset budget for active users (refresh their budget)
                        try:
                            refresh_period_days = int(item.get('refresh_period_days', {{}}).get('N', '30'))
                            next_refresh_date = current_time + timedelta(days=refresh_period_days)
                            
                            user_budgets_table.update_item(
                                Key={{'principal_id': principal_id}},
                                UpdateExpression='SET spent_usd = :zero, budget_period_start = :period_start, budget_refresh_date = :next_refresh, refresh_count = refresh_count + :one',
                                ExpressionAttributeValues={{
                                    ':zero': 0,
                                    ':period_start': current_time.isoformat(),
                                    ':next_refresh': next_refresh_date.isoformat(),
                                    ':one': 1
                                }}
                            )
                            refreshed_count += 1
                            logger.info(f"Refreshed budget for active user: {{principal_id}}")
                        except Exception as e:
                            logger.error(f"Error refreshing budget for {{principal_id}}: {{e}}")
        
        # Publish metrics
        MetricsPublisher.publish_budget_metric(
            'BudgetRefreshCompleted',
            refreshed_count,
            'Count',
            {{'Environment': os.environ['ENVIRONMENT']}}
        )
        
        MetricsPublisher.publish_budget_metric(
            'AutomaticRestorationsTriggered',
            restoration_count,
            'Count',
            {{'Environment': os.environ['ENVIRONMENT']}}
        )
        
        logger.info(f"Budget refresh completed: {{refreshed_count}} refreshed, {{restoration_count}} restorations triggered")
        
        return {{
            'statusCode': 200,
            'refreshed_count': refreshed_count,
            'restoration_count': restoration_count
        }}
        
    except Exception as e:
        logger.error(f"Error in budget refresh: {{e}}", exc_info=True)
        raise
"""
        
        self.lambda_functions["budget_refresh"] = lambda_.Function(
            self,
            "BudgetRefreshFunction",
            function_name=f"bedrock-budgeteer-budget-refresh-{self.environment_name}",
            code=lambda_.Code.from_inline(function_code),
            handler="index.lambda_handler",
            dead_letter_queue=self.dlq_queues["budget_refresh"],
            timeout=Duration.minutes(10),
            **{k: v for k, v in common_config.items() if k != 'timeout'}
        )
    
    def _create_audit_logger_lambda(self, common_config: Dict[str, Any]) -> None:
        """Create Lambda function for audit logging"""
        
        function_code = f"""
{get_shared_lambda_utilities()}

def lambda_handler(event, context):
    \"\"\"Process audit events and store them in the audit logs table\"\"\"
    logger.info("Processing audit event")
    
    try:
        if 'detail' not in event:
            logger.error("Invalid event format - missing detail")
            return {{'statusCode': 400, 'body': 'Invalid event format'}}
        
        detail = event['detail']
        event_source = event.get('source', 'unknown')
        detail_type = event.get('detail-type', 'Unknown Event')
        
        # Create audit log entry
        audit_entry = {{
            'event_id': str(uuid.uuid4()),
            'event_time': datetime.now(timezone.utc).isoformat(),
            'event_source': event_source,
            'event_type': detail_type,
            'principal_id': detail.get('principal_id', 'system'),
            'details': json.dumps(detail, default=str),
            'timestamp_epoch': int(datetime.now(timezone.utc).timestamp())
        }}
        
        # Store in DynamoDB
        audit_logs_table = dynamodb.Table(os.environ['AUDIT_LOGS_TABLE'])
        audit_logs_table.put_item(Item=DynamoDBHelper.float_to_decimal(audit_entry))
        
        MetricsPublisher.publish_budget_metric(
            'AuditEventsProcessed',
            1.0,
            'Count',
            {{'EventSource': event_source, 'Environment': os.environ['ENVIRONMENT']}}
        )
        
        return {{'statusCode': 200, 'body': 'Audit event processed successfully'}}
        
    except Exception as e:
        logger.error(f"Error processing audit event: {{e}}", exc_info=True)
        raise
"""
        
        self.lambda_functions["audit_logger"] = lambda_.Function(
            self,
            "AuditLoggerFunction",
            function_name=f"bedrock-budgeteer-audit-logger-{self.environment_name}",
            code=lambda_.Code.from_inline(function_code),
            handler="index.lambda_handler",
            dead_letter_queue=self.dlq_queues["audit_logger"],
            **common_config
        )
    
    def _create_state_reconciliation_lambda(self, common_config: Dict[str, Any]) -> None:
        """Create Lambda function for state reconciliation"""
        
        function_code = f"""
{get_shared_lambda_utilities()}

def lambda_handler(event, context):
    \"\"\"Reconcile state between IAM policies and DynamoDB budget status\"\"\"
    logger.info("Starting state reconciliation process")
    
    try:
        user_budgets_table = dynamodb.Table(os.environ['USER_BUDGETS_TABLE'])
        
        scan_kwargs = {{}}
        reconciled_users = 0
        
        while True:
            response = user_budgets_table.scan(**scan_kwargs)
            
            for item in response['Items']:
                reconciled_users += 1
                # Basic reconciliation logic would go here
            
            if 'LastEvaluatedKey' in response:
                scan_kwargs['ExclusiveStartKey'] = response['LastEvaluatedKey']
            else:
                break
        
        MetricsPublisher.publish_budget_metric(
            'ReconciledUsers',
            reconciled_users,
            'Count',
            {{'Environment': os.environ['ENVIRONMENT']}}
        )
        
        return {{'statusCode': 200, 'reconciled_users': reconciled_users}}
        
    except Exception as e:
        logger.error(f"Error in state reconciliation: {{e}}", exc_info=True)
        raise
"""
        
        reconciliation_config = common_config.copy()
        reconciliation_config.update({
            "timeout": Duration.minutes(15),
            "memory_size": 256
        })
        
        self.lambda_functions["state_reconciliation"] = lambda_.Function(
            self,
            "StateReconciliationFunction",
            function_name=f"bedrock-budgeteer-state-reconciliation-{self.environment_name}",
            code=lambda_.Code.from_inline(function_code),
            handler="index.lambda_handler", 
            dead_letter_queue=self.dlq_queues["state_reconciliation"],
            **reconciliation_config
        )
    
    def _create_pricing_manager_lambda(self, common_config: Dict[str, Any]) -> None:
        """Create Lambda function for managing Bedrock pricing data"""
        
        function_code = f"""
{get_shared_lambda_utilities()}

def _get_all_foundation_models():
    \"\"\"Get all available Bedrock foundation models\"\"\"
    try:
        # Try to get models from Bedrock API
        bedrock = boto3.client('bedrock', region_name='us-east-1')
        response = bedrock.list_foundation_models()
        
        models = []
        for model in response.get('modelSummaries', []):
            model_id = model.get('modelId')
            if model_id:
                models.append(model_id)
        
        if models:
            logger.info(f"Retrieved {{len(models)}} foundation models from Bedrock API")
            return models
    except Exception as e:
        logger.warning(f"Failed to fetch models from Bedrock API: {{e}}")
    
    # Minimal fallback - only essential Claude models if Bedrock API fails
    essential_models = [
        'anthropic.claude-3-sonnet-20240229-v1:0',      # Most commonly used Claude 3
        'anthropic.claude-3-5-sonnet-20241022-v2:0',    # Latest Claude 3.5
        'anthropic.claude-3-haiku-20240307-v1:0',       # Cost-effective option
        'anthropic.claude-sonnet-4-20250115-v1:0',      # Claude 4 Sonnet
        'anthropic.claude-opus-4-20250115-v1:0',        # Claude 4 Opus
        'anthropic.claude-opus-4-1-20250115-v1:0'       # Claude 4.1 Opus
    ]
    
    logger.warning(f"Bedrock API unavailable - using minimal fallback with {{len(essential_models)}} essential models")
    return essential_models

def lambda_handler(event, context):
    \"\"\"Manage Bedrock pricing data in DynamoDB\"\"\"
    logger.info(f"Pricing manager lambda started with event: {{json.dumps(event)}}")
    
    action = event.get('action', 'daily_refresh')
    source_event = event.get('source_event', {{}})
    
    try:
        # Check if this is triggered by Bedrock API key creation
        if action == 'api_key_triggered':
            # Validate this is a Bedrock API key creation event
            detail = source_event.get('detail', {{}})
            event_name = detail.get('eventName')
            response_elements = detail.get('responseElements', {{}})
            
            # Only process CreateUser events for Bedrock API keys
            if event_name == 'CreateUser' and response_elements:
                user_info = response_elements.get('user', {{}})
                created_user_name = user_info.get('userName', '')
                
                if not created_user_name.startswith('BedrockAPIKey-'):
                    logger.info(f"Ignoring non-Bedrock user creation: {{created_user_name}}")
                    return {{'statusCode': 200, 'body': 'Event ignored - not a Bedrock API key'}}
                
                # Check if pricing table is already populated
                # Only populate on FIRST Bedrock API key creation
                pricing_table = dynamodb.Table(os.environ['PRICING_TABLE'])
                
                try:
                    # Check if any pricing data exists
                    scan_response = pricing_table.scan(Limit=1)
                    existing_items = scan_response.get('Items', [])
                    
                    if existing_items:
                        logger.info(f"Pricing table already populated ({{len(existing_items)}} items exist). Skipping population for user: {{created_user_name}}")
                        return {{'statusCode': 200, 'body': 'Pricing table already populated - skipping'}}
                    
                    logger.info(f"Pricing table is empty. Populating pricing data for first Bedrock API key: {{created_user_name}}")
                    populated_by = 'populated by setup'
                    
                except Exception as e:
                    logger.error(f"Error checking pricing table status: {{e}}")
                    # If we can't check, err on the side of caution and don't populate
                    return {{'statusCode': 500, 'body': 'Error checking pricing table status'}}
            else:
                logger.info(f"Ignoring non-CreateUser event: {{event_name}}")
                return {{'statusCode': 200, 'body': 'Event ignored - not relevant'}}
        
        elif action in ['daily_refresh', 'refresh_all']:
            populated_by = 'populated by event'
            logger.info("Processing daily pricing refresh")
        else:
            logger.warning(f"Unknown action: {{action}}")
            return {{'statusCode': 400, 'body': 'Unknown action'}}
        
        # Fetch ALL foundation models from AWS Pricing API
        # For daily_refresh/refresh_all, we need to get the pricing table reference
        if action in ['daily_refresh', 'refresh_all']:
            pricing_table = dynamodb.Table(os.environ['PRICING_TABLE'])
        
        # Get all available Bedrock foundation models
        all_models = _get_all_foundation_models()
        logger.info(f"Found {{len(all_models)}} foundation models to process")
        
        updated_count = 0
        failed_count = 0
        
        for model_id in all_models:
            try:
                # Try to fetch real pricing from AWS Pricing API first
                pricing_data = BedrockPricingCalculator.fetch_pricing_from_api(model_id, 'us-east-1')
                data_source = 'aws_pricing_api'
                
                # Fall back to static pricing if API fails
                if not pricing_data:
                    logger.warning(f"AWS Pricing API failed for {{model_id}}, using fallback pricing")
                    pricing_data = BedrockPricingCalculator._get_fallback_pricing(model_id)
                    data_source = 'fallback'
                
                ttl = int((datetime.now(timezone.utc) + timedelta(days=1)).timestamp())
                
                pricing_table.put_item(
                    Item={{
                        'model_id': model_id,
                        'region': 'us-east-1',
                        'input_tokens_per_1000': Decimal(str(pricing_data['input_tokens_per_1000'])),
                        'output_tokens_per_1000': Decimal(str(pricing_data['output_tokens_per_1000'])),
                        'last_updated': datetime.now(timezone.utc).isoformat(),
                        'data_source': data_source,
                        'populated_by': populated_by,
                        'ttl': ttl
                    }}
                )
                updated_count += 1
                logger.info(f"Updated pricing for {{model_id}} (source: {{data_source}}, trigger: {{populated_by}}): input=${{pricing_data['input_tokens_per_1000']:.6f}}, output=${{pricing_data['output_tokens_per_1000']:.6f}}")
                
            except Exception as e:
                logger.error(f"Failed to update pricing for {{model_id}}: {{e}}")
                failed_count += 1
        
        logger.info(f"Pricing population completed: {{updated_count}}/{{len(all_models)}} models updated, {{failed_count}} failed")
        return {{'statusCode': 200, 'body': {{'refreshed': updated_count, 'total': len(all_models), 'failed': failed_count, 'populated_by': populated_by}}}}
        
    except Exception as e:
        logger.error(f"Error in pricing manager: {{e}}", exc_info=True)
        return {{'statusCode': 500, 'error': str(e)}}
"""
        
        pricing_config = common_config.copy()
        pricing_config.update({
            "timeout": Duration.minutes(10),
            "memory_size": 256
        })
        
        self.lambda_functions["pricing_manager"] = lambda_.Function(
            self,
            "PricingManagerFunction",
            function_name=f"bedrock-budgeteer-pricing-manager-{self.environment_name}",
            code=lambda_.Code.from_inline(function_code),
            handler="index.lambda_handler",
            **pricing_config
        )
        

    
    def _setup_event_routing(self) -> None:
        """Set up EventBridge rules to route events to Lambda functions"""
        
        # User setup events
        events.Rule(
            self,
            "UserSetupEventRule",
            rule_name=f"bedrock-budgeteer-user-setup-{self.environment_name}",
            description="Route IAM and Bedrock API key creation events to user setup and pricing Lambda",
            event_pattern=events.EventPattern(
                source=["aws.iam"],
                detail_type=["AWS API Call via CloudTrail"],
                detail={
                    "eventName": [
                        "CreateUser",
                        "CreateServiceSpecificCredential",
                        "CreateAccessKey",
                        "AttachUserPolicy", 
                        "AttachRolePolicy",
                        "PutUserPolicy",
                        "PutRolePolicy"
                    ]
                }
            ),
            targets=[
                targets.LambdaFunction(self.lambda_functions["user_setup"]),
                targets.LambdaFunction(
                    self.lambda_functions["pricing_manager"],
                    event=events.RuleTargetInput.from_object({
                        "action": "api_key_triggered",
                        "source_event": {
                            "detail": events.EventField.from_path("$.detail"),
                            "source": events.EventField.from_path("$.source"),
                            "detail-type": events.EventField.from_path("$.detail-type")
                        }
                    })
                )
            ]
        )
        
        # Audit events
        events.Rule(
            self,
            "AuditEventRule", 
            rule_name=f"bedrock-budgeteer-audit-{self.environment_name}",
            description="Route all system events to audit logger",
            event_pattern=events.EventPattern(
                source=["bedrock-budgeteer"]
            ),
            targets=[targets.LambdaFunction(self.lambda_functions["audit_logger"])]
        )
    
    def _create_monitoring_schedule(self) -> None:
        """Create CloudWatch Events schedule for monitoring functions"""
        
        # Budget monitoring schedule (every 5 minutes)
        events.Rule(
            self,
            "BudgetMonitoringSchedule",
            rule_name=f"bedrock-budgeteer-monitor-schedule-{self.environment_name}",
            description="Schedule for budget monitoring Lambda",
            schedule=events.Schedule.rate(Duration.minutes(5)),
            targets=[targets.LambdaFunction(self.lambda_functions["budget_monitor"])]
        )
        
        # State reconciliation schedule (every 4 hours)
        events.Rule(
            self,
            "StateReconciliationSchedule",
            rule_name=f"bedrock-budgeteer-reconciliation-schedule-{self.environment_name}",
            description="Schedule for state reconciliation Lambda",
            schedule=events.Schedule.rate(Duration.hours(4)),
            targets=[targets.LambdaFunction(self.lambda_functions["state_reconciliation"])]
        )
        
        # Budget refresh schedule (daily at 2 AM UTC)
        events.Rule(
            self,
            "BudgetRefreshSchedule",
            rule_name=f"bedrock-budgeteer-refresh-schedule-{self.environment_name}",
            description="Schedule for budget refresh Lambda",
            schedule=events.Schedule.cron(minute="0", hour="2"),
            targets=[targets.LambdaFunction(self.lambda_functions["budget_refresh"])]
        )
        
        # Pricing refresh schedule (daily at 1 AM UTC)
        events.Rule(
            self,
            "PricingRefreshSchedule",
            rule_name=f"bedrock-budgeteer-pricing-refresh-{self.environment_name}",
            description="Schedule for pricing refresh Lambda",
            schedule=events.Schedule.cron(minute="0", hour="1"),
            targets=[targets.LambdaFunction(
                self.lambda_functions["pricing_manager"],
                event=events.RuleTargetInput.from_object({"action": "refresh_all"})
            )]
        )
    
    # Public properties to expose resources (maintain API compatibility)
    @property
    def functions(self) -> Dict[str, lambda_.Function]:
        """Expose Lambda functions for use by other constructs"""
        return self.lambda_functions
    
    @property
    def dead_letter_queues(self) -> Dict[str, sqs.Queue]:
        """Expose DLQ queues for monitoring"""
        return self.dlq_queues
    
    @property
    def execution_role(self) -> iam.Role:
        """Expose execution role for additional permissions"""
        return self.lambda_execution_role
