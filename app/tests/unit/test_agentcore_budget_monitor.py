"""Tests for AgentCore budget monitor Lambda function code"""
import unittest


class TestAgentCoreBudgetMonitorContent(unittest.TestCase):
    """Validate agentcore_budget_monitor Lambda code"""

    def setUp(self):
        from app.constructs.lambda_functions.agentcore_budget_monitor import (
            get_agentcore_budget_monitor_function_code
        )
        self.code = get_agentcore_budget_monitor_function_code()

    def test_contains_lambda_handler(self):
        self.assertIn('def lambda_handler(event, context):', self.code)

    def test_scans_agentcore_table(self):
        self.assertIn('AGENTCORE_BUDGETS_TABLE', self.code)

    def test_separates_global_pool(self):
        self.assertIn('GLOBAL_POOL', self.code)

    def test_checks_per_agent_budgets(self):
        self.assertIn('budget_limit_usd', self.code)
        self.assertIn('spent_usd', self.code)

    def test_checks_pool_capacity(self):
        self.assertIn('pool_spent', self.code)

    def test_checks_global_cap(self):
        self.assertIn('global_usage_percent', self.code)

    def test_triggers_suspension_workflow(self):
        self.assertIn('AGENTCORE_SUSPENSION_STATE_MACHINE_ARN', self.code)

    def test_grace_period_logic(self):
        self.assertIn('grace_deadline_epoch', self.code)
        self.assertIn('grace_period_seconds', self.code)

    def test_threshold_states(self):
        self.assertIn('warning', self.code)
        self.assertIn('critical', self.code)

    def test_publishes_metrics(self):
        self.assertIn('MonitoredAgentRuntimes', self.code)
        self.assertIn('AgentBudgetExceeded', self.code)
        self.assertIn('AgentPoolUtilizationPercent', self.code)

    def test_batch_suspension_for_pool(self):
        self.assertIn('suspend_unbudgeted_runtimes', self.code)

    def test_checks_budget_refreshes(self):
        self.assertIn('_check_budget_refreshes', self.code)
        self.assertIn('budget_refresh_date', self.code)

    def test_triggers_restoration_workflow(self):
        self.assertIn('AGENTCORE_RESTORATION_STATE_MACHINE_ARN', self.code)
        self.assertIn('_trigger_restoration_workflow', self.code)


if __name__ == '__main__':
    unittest.main()
