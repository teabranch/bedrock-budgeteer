"""Tests for AgentCore setup Lambda function code"""
import unittest


class TestAgentCoreSetupContent(unittest.TestCase):
    """Validate agentcore_setup Lambda code contains required logic"""

    def setUp(self):
        from app.constructs.lambda_functions.agentcore_setup import get_agentcore_setup_function_code
        self.code = get_agentcore_setup_function_code()

    def test_contains_lambda_handler(self):
        self.assertIn('def lambda_handler(event, context):', self.code)

    def test_handles_create_agent_runtime(self):
        self.assertIn('CreateAgentRuntime', self.code)

    def test_handles_delete_agent_runtime(self):
        self.assertIn('DeleteAgentRuntime', self.code)

    def test_handles_update_agent_runtime(self):
        self.assertIn('UpdateAgentRuntime', self.code)

    def test_extracts_runtime_id(self):
        self.assertIn('agentRuntimeId', self.code)

    def test_extracts_role_arn(self):
        self.assertIn('roleArn', self.code)

    def test_creates_global_pool(self):
        self.assertIn('GLOBAL_POOL', self.code)

    def test_idempotency_check(self):
        self.assertIn('ConditionExpression', self.code)

    def test_publishes_audit_event(self):
        self.assertIn('EventPublisher', self.code)

    def test_publishes_metrics(self):
        self.assertIn('MetricsPublisher', self.code)

    def test_contains_required_imports(self):
        self.assertIn('import json', self.code)
        self.assertIn('import boto3', self.code)
        self.assertIn('from decimal import Decimal', self.code)


if __name__ == '__main__':
    unittest.main()
