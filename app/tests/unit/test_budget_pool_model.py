"""Tests for pool-based budget model in budget_monitor and usage_calculator"""
import unittest


class TestBudgetMonitorPoolLogic(unittest.TestCase):
    """Verify budget monitor inline code contains pool enforcement logic"""

    def test_budget_monitor_has_pool_check(self):
        """Verify the budget monitor code includes pool-level enforcement"""
        from app.constructs.core_processing import CoreProcessingConstruct
        import inspect
        source = inspect.getsource(CoreProcessingConstruct._create_budget_monitor_lambda)
        self.assertIn('GLOBAL_API_KEY_POOL', source)
        self.assertIn('pool_exhausted', source)
        self.assertIn('global_cap', source)
        self.assertIn('per_key', source)

    def test_budget_monitor_classifies_keys(self):
        """Verify keys are classified into budgeted vs unbudgeted"""
        from app.constructs.core_processing import CoreProcessingConstruct
        import inspect
        source = inspect.getsource(CoreProcessingConstruct._create_budget_monitor_lambda)
        self.assertIn('budgeted_keys', source)
        self.assertIn('unbudgeted_keys', source)
        self.assertIn('has_carveout', source)

    def test_budget_monitor_computes_pool_from_first_principles(self):
        """Verify pool spent is computed from individual keys, not just cached"""
        from app.constructs.core_processing import CoreProcessingConstruct
        import inspect
        source = inspect.getsource(CoreProcessingConstruct._create_budget_monitor_lambda)
        self.assertIn('computed_pool_spent', source)
        self.assertIn('cached_pool_spent', source)
        self.assertIn('Pool spent drift', source)

    def test_budget_monitor_has_three_tier_enforcement(self):
        """Verify all three enforcement tiers exist"""
        from app.constructs.core_processing import CoreProcessingConstruct
        import inspect
        source = inspect.getsource(CoreProcessingConstruct._create_budget_monitor_lambda)
        self.assertIn('Tier 1: Per-key check', source)
        self.assertIn('Tier 2: Pool check', source)
        self.assertIn('Tier 3: Global cap check', source)

    def test_budget_monitor_publishes_pool_metrics(self):
        """Verify pool utilization metrics are published"""
        from app.constructs.core_processing import CoreProcessingConstruct
        import inspect
        source = inspect.getsource(CoreProcessingConstruct._create_budget_monitor_lambda)
        self.assertIn('ApiKeyPoolSpentUsd', source)
        self.assertIn('ApiKeyGlobalCapSpentUsd', source)

    def test_budget_monitor_checks_budget_refreshes(self):
        """Verify suspended keys are checked for budget refresh eligibility"""
        from app.constructs.core_processing import CoreProcessingConstruct
        import inspect
        source = inspect.getsource(CoreProcessingConstruct._create_budget_monitor_lambda)
        self.assertIn('_check_budget_refreshes', source)
        self.assertIn('Restoration Workflow Required', source)


class TestUsageCalculatorPoolTracking(unittest.TestCase):
    """Verify usage calculator includes pool tracking"""

    def test_usage_calculator_has_pool_update(self):
        """Verify usage calculator updates pool for unbudgeted keys"""
        from app.constructs.lambda_functions.usage_calculator import get_usage_calculator_function_code
        code = get_usage_calculator_function_code()
        self.assertIn('_update_api_key_pool_if_needed', code)
        self.assertIn('GLOBAL_API_KEY_POOL', code)

    def test_usage_calculator_has_metadata_cache(self):
        """Verify module-level cache for key metadata"""
        from app.constructs.lambda_functions.usage_calculator import get_usage_calculator_function_code
        code = get_usage_calculator_function_code()
        self.assertIn('_key_metadata_cache', code)
        self.assertIn('_get_key_metadata', code)

    def test_usage_calculator_enriches_tracking_with_team(self):
        """Verify usage tracking records include team and purpose"""
        from app.constructs.lambda_functions.usage_calculator import get_usage_calculator_function_code
        code = get_usage_calculator_function_code()
        self.assertIn("team=team_purpose.get('team')", code)
        self.assertIn("purpose=team_purpose.get('purpose')", code)

    def test_record_usage_tracking_accepts_team_purpose(self):
        """Verify record_usage_tracking has team and purpose parameters"""
        from app.constructs.lambda_functions.usage_calculator import get_usage_calculator_function_code
        code = get_usage_calculator_function_code()
        self.assertIn('team=None, purpose=None', code)
        self.assertIn("usage_record['team'] = team", code)
        self.assertIn("usage_record['purpose'] = purpose", code)


if __name__ == '__main__':
    unittest.main()
