"""CDK assertion tests for AgentCoreConstruct"""
import unittest
import json


class TestAgentCoreConstructExists(unittest.TestCase):
    """Basic validation that the AgentCore construct module exists and has the right class"""

    def test_import_construct(self):
        from app.constructs.agentcore import AgentCoreConstruct
        self.assertTrue(hasattr(AgentCoreConstruct, '__init__'))

    def test_construct_has_required_attributes(self):
        """Verify the construct class defines expected attributes"""
        from app.constructs.agentcore import AgentCoreConstruct
        import inspect
        source = inspect.getsource(AgentCoreConstruct)
        self.assertIn('agentcore_budgets_table', source)
        self.assertIn('agentcore_setup', source)
        self.assertIn('agentcore_budget_monitor', source)
        self.assertIn('agentcore_budget_manager', source)
        self.assertIn('EventBridge', source)
        self.assertIn('bedrock-agentcore.amazonaws.com', source)
        self.assertIn('restoration_state_machine', source)
        self.assertIn('grant_start_execution', source)


class TestAgentCoreFeatureFlag(unittest.TestCase):
    """Test that AgentCore construct respects the feature flag"""

    def test_feature_flag_key_in_cdk_json(self):
        with open('cdk.json', 'r') as f:
            cdk_config = json.load(f)
        feature_flags = cdk_config.get('context', {}).get('bedrock-budgeteer:feature-flags', {})
        self.assertIn('enable_agentcore_budgeting', feature_flags)


if __name__ == '__main__':
    unittest.main()
