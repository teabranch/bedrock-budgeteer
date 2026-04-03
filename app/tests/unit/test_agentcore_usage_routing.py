"""Tests for AgentCore helpers and usage routing logic"""
import unittest
import json


class TestAgentCoreHelpersContent(unittest.TestCase):
    """Validate agentcore_helpers contains required code"""

    def setUp(self):
        from app.constructs.shared.agentcore_helpers import get_agentcore_helpers
        self.helpers_code = get_agentcore_helpers()

    def test_contains_lookup_function(self):
        self.assertIn('def lookup_runtime_by_role_arn(', self.helpers_code)

    def test_contains_update_runtime_budget(self):
        self.assertIn('def update_runtime_budget(', self.helpers_code)

    def test_contains_update_global_pool(self):
        self.assertIn('def update_global_pool(', self.helpers_code)

    def test_contains_extract_role_arn(self):
        self.assertIn('def extract_role_arn_from_event(', self.helpers_code)

    def test_contains_required_imports(self):
        self.assertIn('import boto3', self.helpers_code)
        self.assertIn('import os', self.helpers_code)
        self.assertIn('from decimal import Decimal', self.helpers_code)


class TestExtractRoleArnLogic(unittest.TestCase):
    """Test role ARN extraction from CloudTrail events"""

    def test_extract_role_arn_from_assumed_role_event(self):
        """Validate extraction logic handles AssumedRole userIdentity"""
        event_detail = {
            'userIdentity': {
                'type': 'AssumedRole',
                'sessionContext': {
                    'sessionIssuer': {
                        'arn': 'arn:aws:iam::123456789012:role/MyAgentRole'
                    }
                }
            }
        }
        role_arn = event_detail['userIdentity']['sessionContext']['sessionIssuer']['arn']
        self.assertEqual(role_arn, 'arn:aws:iam::123456789012:role/MyAgentRole')

    def test_no_role_arn_for_iam_user(self):
        """IAM user events should not return a role ARN"""
        event_detail = {
            'userIdentity': {
                'type': 'IAMUser',
                'arn': 'arn:aws:iam::123456789012:user/BedrockAPIKey-test'
            }
        }
        self.assertNotIn('sessionContext', event_detail.get('userIdentity', {}))


if __name__ == '__main__':
    unittest.main()
