"""Tests for AgentCore budget manager Lambda function code"""
import unittest


class TestAgentCoreBudgetManagerContent(unittest.TestCase):
    """Validate agentcore_budget_manager Lambda code"""

    def setUp(self):
        from app.constructs.lambda_functions.agentcore_budget_manager import (
            get_agentcore_budget_manager_function_code
        )
        self.code = get_agentcore_budget_manager_function_code()

    def test_contains_lambda_handler(self):
        self.assertIn('def lambda_handler(event, context):', self.code)

    def test_handles_set_agent_budget(self):
        self.assertIn('set_agent_budget', self.code)

    def test_handles_remove_agent_budget(self):
        self.assertIn('remove_agent_budget', self.code)

    def test_handles_set_global_budget(self):
        self.assertIn('set_global_budget', self.code)

    def test_handles_get_budget_status(self):
        self.assertIn('get_budget_status', self.code)

    def test_validates_budget_not_exceeds_global(self):
        self.assertIn('exceeds global', self.code.lower())

    def test_validates_global_not_below_allocated(self):
        self.assertIn('allocated', self.code.lower())

    def test_returns_json_response(self):
        self.assertIn('"success"', self.code)
        self.assertIn('"error"', self.code)

    def test_publishes_audit_events(self):
        self.assertIn('EventPublisher', self.code)

    def test_parses_function_url_body(self):
        self.assertIn('body', self.code)


if __name__ == '__main__':
    unittest.main()
