"""
Unit tests for user_setup Lambda: rogue key detection, CDK provisioning,
global pool management, and tag change handling.

Uses unittest.mock to patch boto3 clients and DynamoDB table interactions
since the Lambda code is returned as inline strings (not directly importable).
"""
import unittest
from unittest.mock import patch, MagicMock, call
import json
import os
from decimal import Decimal
from datetime import datetime, timezone, timedelta


def _build_exec_env():
    """Build a namespace that simulates the shared-utilities + user_setup Lambda."""
    from app.constructs.shared.lambda_utilities import get_shared_lambda_utilities
    from app.constructs.lambda_functions.user_setup import get_user_setup_function_code

    shared_code = get_shared_lambda_utilities()
    function_code = get_user_setup_function_code()
    combined = f"{shared_code}\n\n{function_code}"
    namespace = {}
    exec(compile(combined, '<user_setup_lambda>', 'exec'), namespace)
    return namespace


def _make_event(event_name, user_name, extra_detail=None):
    """Build a minimal EventBridge-wrapped CloudTrail event."""
    detail = {
        'eventName': event_name,
        'userIdentity': {
            'arn': 'arn:aws:iam::123456789012:user/admin',
            'userName': 'admin',
        },
        'eventTime': '2026-04-13T10:00:00Z',
        'sourceIPAddress': '198.51.100.1',
        'requestParameters': {'userName': user_name},
        'responseElements': {
            'user': {'userName': user_name, 'arn': f'arn:aws:iam::123456789012:user/{user_name}'}
        },
    }
    if extra_detail:
        detail.update(extra_detail)
    return {'detail': detail}


class TestCdkProvisionedKeyDetected(unittest.TestCase):
    """When IAM tags include Provisioned=cdk the budget should have has_carveout=True."""

    @patch.dict(os.environ, {
        'ENVIRONMENT': 'test',
        'USER_BUDGETS_TABLE': 'user-budgets',
        'BUDGET_ALERTS_SNS_TOPIC_ARN': 'arn:aws:sns:us-east-1:123456789012:alerts',
    })
    @patch('boto3.client')
    @patch('boto3.resource')
    def test_cdk_provisioned_key_detected(self, mock_resource, mock_client):
        # -- arrange --
        mock_table = MagicMock()
        mock_table.get_item.return_value = {}  # no existing budget
        mock_resource.return_value.Table.return_value = mock_table

        mock_iam = MagicMock()
        mock_iam.list_user_tags.return_value = {
            'Tags': [
                {'Key': 'BedrockBudgeteer:Provisioned', 'Value': 'cdk'},
                {'Key': 'BedrockBudgeteer:Team', 'Value': 'ml-platform'},
                {'Key': 'BedrockBudgeteer:Purpose', 'Value': 'inference'},
                {'Key': 'BedrockBudgeteer:BudgetTier', 'Value': 'standard'},
            ]
        }

        mock_ssm = MagicMock()
        mock_ssm.get_parameter.return_value = {'Parameter': {'Value': '100'}}

        mock_cw = MagicMock()
        mock_events = MagicMock()
        mock_sns = MagicMock()

        def _client_factory(service, **kwargs):
            return {
                'iam': mock_iam,
                'ssm': mock_ssm,
                'cloudwatch': mock_cw,
                'events': mock_events,
                'sns': mock_sns,
            }.get(service, MagicMock())

        mock_client.side_effect = _client_factory

        ns = _build_exec_env()

        # Patch the module-level clients that were created during exec
        ns['iam_client'] = mock_iam
        ns['sns_client'] = mock_sns
        ns['dynamodb'] = mock_resource.return_value
        ns['ssm'] = mock_ssm
        ns['cloudwatch'] = mock_cw
        ns['events'] = mock_events

        event = _make_event('CreateUser', 'BedrockAPIKey-abc123')
        context = MagicMock()

        # -- act --
        result = ns['lambda_handler'](event, context)

        # -- assert --
        self.assertEqual(result['statusCode'], 200)

        put_calls = mock_table.put_item.call_args_list
        # Should have two put_item calls: GLOBAL_API_KEY_POOL and the key budget
        self.assertGreaterEqual(len(put_calls), 1)

        # Find the budget item (not the pool)
        budget_items = [
            c for c in put_calls
            if c.kwargs.get('Item', {}).get('principal_id') == 'BedrockAPIKey-abc123'
            or (c.args and c.args[0].get('Item', {}).get('principal_id') == 'BedrockAPIKey-abc123')
        ]
        self.assertEqual(len(budget_items), 1)

        item = budget_items[0].kwargs.get('Item') or budget_items[0][1]['Item']
        self.assertTrue(item['has_carveout'])
        self.assertEqual(item['provisioned_by'], 'cdk')
        self.assertEqual(item['team'], 'ml-platform')
        self.assertIn('budget_limit_usd', item)

        # IAM tag_user should NOT have been called (not rogue)
        mock_iam.tag_user.assert_not_called()


class TestScriptProvisionedKeyDetected(unittest.TestCase):
    """When IAM tags include Provisioned=script the key should be treated as provisioned (not rogue)."""

    @patch.dict(os.environ, {
        'ENVIRONMENT': 'test',
        'USER_BUDGETS_TABLE': 'user-budgets',
        'BUDGET_ALERTS_SNS_TOPIC_ARN': 'arn:aws:sns:us-east-1:123456789012:alerts',
    })
    @patch('boto3.client')
    @patch('boto3.resource')
    def test_script_provisioned_key_detected(self, mock_resource, mock_client):
        mock_table = MagicMock()
        mock_table.get_item.return_value = {}
        mock_resource.return_value.Table.return_value = mock_table

        mock_iam = MagicMock()
        mock_iam.list_user_tags.return_value = {
            'Tags': [
                {'Key': 'BedrockBudgeteer:Provisioned', 'Value': 'script'},
                {'Key': 'BedrockBudgeteer:Team', 'Value': 'data-eng'},
                {'Key': 'BedrockBudgeteer:Purpose', 'Value': 'etl-pipeline'},
                {'Key': 'BedrockBudgeteer:BudgetTier', 'Value': 'high'},
            ]
        }

        mock_ssm = MagicMock()
        mock_ssm.get_parameter.return_value = {'Parameter': {'Value': '25'}}

        mock_cw = MagicMock()
        mock_events = MagicMock()
        mock_sns = MagicMock()

        def _client_factory(service, **kwargs):
            return {
                'iam': mock_iam, 'ssm': mock_ssm, 'cloudwatch': mock_cw,
                'events': mock_events, 'sns': mock_sns,
            }.get(service, MagicMock())

        mock_client.side_effect = _client_factory

        ns = _build_exec_env()
        ns['iam_client'] = mock_iam
        ns['sns_client'] = mock_sns
        ns['dynamodb'] = mock_resource.return_value
        ns['ssm'] = mock_ssm
        ns['cloudwatch'] = mock_cw
        ns['events'] = mock_events

        event = _make_event('CreateUser', 'BedrockAPIKey-data-eng-etl-pipeline')
        result = ns['lambda_handler'](event, MagicMock())

        self.assertEqual(result['statusCode'], 200)

        put_calls = mock_table.put_item.call_args_list
        budget_items = [
            c for c in put_calls
            if c.kwargs.get('Item', {}).get('principal_id') == 'BedrockAPIKey-data-eng-etl-pipeline'
            or (c.args and c.args[0].get('Item', {}).get('principal_id') == 'BedrockAPIKey-data-eng-etl-pipeline')
        ]
        self.assertEqual(len(budget_items), 1)

        item = budget_items[0].kwargs.get('Item') or budget_items[0][1]['Item']
        self.assertTrue(item['has_carveout'])
        self.assertEqual(item['provisioned_by'], 'script')
        self.assertEqual(item['team'], 'data-eng')

        # Not rogue — tag_user should NOT have been called
        mock_iam.tag_user.assert_not_called()


class TestRogueKeyDetected(unittest.TestCase):
    """When IAM tags are missing, the key should be tagged and an SNS alert published."""

    @patch.dict(os.environ, {
        'ENVIRONMENT': 'test',
        'USER_BUDGETS_TABLE': 'user-budgets',
        'BUDGET_ALERTS_SNS_TOPIC_ARN': 'arn:aws:sns:us-east-1:123456789012:alerts',
    })
    @patch('boto3.client')
    @patch('boto3.resource')
    @patch('time.sleep', return_value=None)  # skip the retry delay
    def test_rogue_key_detected(self, mock_sleep, mock_resource, mock_client):
        mock_table = MagicMock()
        mock_table.get_item.return_value = {}
        mock_resource.return_value.Table.return_value = mock_table

        mock_iam = MagicMock()
        # No tags at all — both attempts return empty
        mock_iam.list_user_tags.return_value = {'Tags': []}

        mock_ssm = MagicMock()
        mock_ssm.get_parameter.return_value = {'Parameter': {'Value': '500'}}

        mock_cw = MagicMock()
        mock_events = MagicMock()
        mock_sns = MagicMock()

        def _client_factory(service, **kwargs):
            return {
                'iam': mock_iam,
                'ssm': mock_ssm,
                'cloudwatch': mock_cw,
                'events': mock_events,
                'sns': mock_sns,
            }.get(service, MagicMock())

        mock_client.side_effect = _client_factory

        ns = _build_exec_env()
        ns['iam_client'] = mock_iam
        ns['sns_client'] = mock_sns
        ns['dynamodb'] = mock_resource.return_value
        ns['ssm'] = mock_ssm
        ns['cloudwatch'] = mock_cw
        ns['events'] = mock_events

        event = _make_event('CreateUser', 'BedrockAPIKey-rogue1')
        result = ns['lambda_handler'](event, MagicMock())

        self.assertEqual(result['statusCode'], 200)

        # tag_user should have been called with default tags
        mock_iam.tag_user.assert_called_once()
        tag_call_kwargs = mock_iam.tag_user.call_args.kwargs
        self.assertEqual(tag_call_kwargs['UserName'], 'BedrockAPIKey-rogue1')
        tag_keys = {t['Key'] for t in tag_call_kwargs['Tags']}
        self.assertIn('BedrockBudgeteer:Provisioned', tag_keys)
        self.assertIn('BedrockBudgeteer:ManagedBy', tag_keys)

        # SNS alert should have been published
        mock_sns.publish.assert_called_once()
        sns_kwargs = mock_sns.publish.call_args.kwargs
        self.assertIn('Rogue', sns_kwargs['Subject'])

        # Budget should have has_carveout=False
        budget_items = [
            c for c in mock_table.put_item.call_args_list
            if c.kwargs.get('Item', {}).get('principal_id') == 'BedrockAPIKey-rogue1'
        ]
        self.assertEqual(len(budget_items), 1)
        item = budget_items[0].kwargs['Item']
        self.assertFalse(item['has_carveout'])
        self.assertNotIn('budget_limit_usd', item)


class TestGlobalPoolCreation(unittest.TestCase):
    """Verify the GLOBAL_API_KEY_POOL row is created in DynamoDB."""

    @patch.dict(os.environ, {
        'ENVIRONMENT': 'test',
        'USER_BUDGETS_TABLE': 'user-budgets',
        'BUDGET_ALERTS_SNS_TOPIC_ARN': '',
    })
    @patch('boto3.client')
    @patch('boto3.resource')
    @patch('time.sleep', return_value=None)
    def test_global_pool_created(self, mock_sleep, mock_resource, mock_client):
        mock_table = MagicMock()
        mock_table.get_item.return_value = {}
        mock_resource.return_value.Table.return_value = mock_table

        mock_iam = MagicMock()
        mock_iam.list_user_tags.return_value = {'Tags': []}

        mock_ssm = MagicMock()
        mock_ssm.get_parameter.return_value = {'Parameter': {'Value': '500'}}

        mock_cw = MagicMock()
        mock_events = MagicMock()
        mock_sns = MagicMock()

        def _client_factory(service, **kwargs):
            return {
                'iam': mock_iam, 'ssm': mock_ssm, 'cloudwatch': mock_cw,
                'events': mock_events, 'sns': mock_sns,
            }.get(service, MagicMock())

        mock_client.side_effect = _client_factory

        ns = _build_exec_env()
        ns['iam_client'] = mock_iam
        ns['sns_client'] = mock_sns
        ns['dynamodb'] = mock_resource.return_value
        ns['ssm'] = mock_ssm
        ns['cloudwatch'] = mock_cw
        ns['events'] = mock_events

        event = _make_event('CreateUser', 'BedrockAPIKey-pool-test')
        ns['lambda_handler'](event, MagicMock())

        pool_items = [
            c for c in mock_table.put_item.call_args_list
            if c.kwargs.get('Item', {}).get('principal_id') == 'GLOBAL_API_KEY_POOL'
        ]
        self.assertEqual(len(pool_items), 1)
        pool_item = pool_items[0].kwargs['Item']
        self.assertEqual(pool_item['account_type'], 'api_key_pool')
        self.assertEqual(pool_item['status'], 'active')
        self.assertEqual(pool_item['spent_usd'], Decimal('0'))


class TestGlobalPoolIdempotent(unittest.TestCase):
    """Calling the pool creation twice should not create a duplicate."""

    @patch.dict(os.environ, {
        'ENVIRONMENT': 'test',
        'USER_BUDGETS_TABLE': 'user-budgets',
        'BUDGET_ALERTS_SNS_TOPIC_ARN': '',
    })
    @patch('boto3.client')
    @patch('boto3.resource')
    def test_global_pool_idempotent(self, mock_resource, mock_client):
        mock_table = MagicMock()
        mock_resource.return_value.Table.return_value = mock_table

        mock_ssm = MagicMock()
        mock_ssm.get_parameter.return_value = {'Parameter': {'Value': '500'}}

        mock_cw = MagicMock()
        mock_events = MagicMock()

        def _client_factory(service, **kwargs):
            return {
                'ssm': mock_ssm, 'cloudwatch': mock_cw,
                'events': mock_events, 'iam': MagicMock(), 'sns': MagicMock(),
            }.get(service, MagicMock())

        mock_client.side_effect = _client_factory

        ns = _build_exec_env()
        ns['dynamodb'] = mock_resource.return_value
        ns['ssm'] = mock_ssm
        ns['cloudwatch'] = mock_cw
        ns['events'] = mock_events

        # First call succeeds
        ns['_ensure_global_api_key_pool'](mock_table)

        # Second call: simulate ConditionalCheckFailedException
        from botocore.exceptions import ClientError
        cond_error = ClientError(
            {'Error': {'Code': 'ConditionalCheckFailedException', 'Message': 'exists'}},
            'PutItem'
        )
        mock_table.put_item.side_effect = cond_error
        # Should not raise
        ns['_ensure_global_api_key_pool'](mock_table)


class TestTagChangeReappliesTags(unittest.TestCase):
    """When a TagUser/UntagUser event removes the Provisioned tag, it should be re-applied."""

    @patch.dict(os.environ, {
        'ENVIRONMENT': 'test',
        'USER_BUDGETS_TABLE': 'user-budgets',
        'BUDGET_ALERTS_SNS_TOPIC_ARN': 'arn:aws:sns:us-east-1:123456789012:alerts',
    })
    @patch('boto3.client')
    @patch('boto3.resource')
    def test_tag_change_event_reapplies_tags(self, mock_resource, mock_client):
        mock_table = MagicMock()
        # Budget already exists
        mock_table.get_item.return_value = {
            'Item': {
                'principal_id': 'BedrockAPIKey-tampered',
                'account_type': 'bedrock_api_key',
                'status': 'active',
            }
        }
        mock_resource.return_value.Table.return_value = mock_table

        mock_iam = MagicMock()
        # Tags after tampering: Provisioned tag is missing
        mock_iam.list_user_tags.return_value = {
            'Tags': [
                {'Key': 'BedrockBudgeteer:Team', 'Value': 'data-science'},
            ]
        }

        mock_ssm = MagicMock()
        mock_cw = MagicMock()
        mock_events = MagicMock()
        mock_sns = MagicMock()

        def _client_factory(service, **kwargs):
            return {
                'iam': mock_iam, 'ssm': mock_ssm, 'cloudwatch': mock_cw,
                'events': mock_events, 'sns': mock_sns,
            }.get(service, MagicMock())

        mock_client.side_effect = _client_factory

        ns = _build_exec_env()
        ns['iam_client'] = mock_iam
        ns['sns_client'] = mock_sns
        ns['dynamodb'] = mock_resource.return_value
        ns['ssm'] = mock_ssm
        ns['cloudwatch'] = mock_cw
        ns['events'] = mock_events

        event = _make_event('UntagUser', 'BedrockAPIKey-tampered')
        result = ns['lambda_handler'](event, MagicMock())

        self.assertEqual(result['statusCode'], 200)
        self.assertEqual(result['body'], 'Tag change processed')

        # Provisioned tag should have been re-applied
        mock_iam.tag_user.assert_called_once()
        reapplied_tags = mock_iam.tag_user.call_args.kwargs['Tags']
        self.assertEqual(reapplied_tags[0]['Key'], 'BedrockBudgeteer:Provisioned')

        # SNS tampering alert should have been sent
        mock_sns.publish.assert_called_once()
        self.assertIn('Tampering', mock_sns.publish.call_args.kwargs['Subject'])

        # DynamoDB should have been updated with current tag values
        mock_table.update_item.assert_called_once()


class TestNonBedrockKeyIgnored(unittest.TestCase):
    """Events for non-BedrockAPIKey users should be skipped."""

    @patch.dict(os.environ, {
        'ENVIRONMENT': 'test',
        'USER_BUDGETS_TABLE': 'user-budgets',
        'BUDGET_ALERTS_SNS_TOPIC_ARN': '',
    })
    @patch('boto3.client')
    @patch('boto3.resource')
    def test_non_bedrock_key_ignored(self, mock_resource, mock_client):
        mock_table = MagicMock()
        mock_resource.return_value.Table.return_value = mock_table

        def _client_factory(service, **kwargs):
            return MagicMock()

        mock_client.side_effect = _client_factory

        ns = _build_exec_env()
        ns['dynamodb'] = mock_resource.return_value

        event = _make_event('CreateUser', 'regular-iam-user')
        result = ns['lambda_handler'](event, MagicMock())

        self.assertEqual(result['statusCode'], 200)
        self.assertIn('not a Bedrock API key', result['body'])

        # No DynamoDB writes should have happened
        mock_table.put_item.assert_not_called()
        mock_table.get_item.assert_not_called()


if __name__ == '__main__':
    unittest.main()
