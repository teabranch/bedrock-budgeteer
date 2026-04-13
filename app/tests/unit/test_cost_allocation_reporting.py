"""Tests for CostAllocationReportingConstruct and feature flag gating"""
import unittest
import json


class TestCostAllocationConstructExists(unittest.TestCase):
    """Basic validation that the cost allocation reporting construct exists"""

    def test_import_construct(self):
        from app.constructs.cost_allocation_reporting import CostAllocationReportingConstruct
        self.assertTrue(hasattr(CostAllocationReportingConstruct, '__init__'))

    def test_construct_has_required_attributes(self):
        """Verify the construct class defines expected components"""
        from app.constructs.cost_allocation_reporting import CostAllocationReportingConstruct
        import inspect
        source = inspect.getsource(CostAllocationReportingConstruct)
        self.assertIn('cost_allocation_sync', source)
        self.assertIn('cost_reconciliation', source)
        self.assertIn('CostAllocationSyncSchedule', source)
        self.assertIn('CostReconciliationSchedule', source)
        self.assertIn('DLQ', source)


class TestCostAllocationFeatureFlag(unittest.TestCase):
    """Test that cost allocation respects the feature flag"""

    def test_feature_flag_key_in_cdk_json(self):
        with open('cdk.json', 'r') as f:
            cdk_config = json.load(f)
        feature_flags = cdk_config.get('context', {}).get('bedrock-budgeteer:feature-flags', {})
        self.assertIn('enable_cost_allocation_reporting', feature_flags)

    def test_key_provisioning_flag_in_cdk_json(self):
        with open('cdk.json', 'r') as f:
            cdk_config = json.load(f)
        feature_flags = cdk_config.get('context', {}).get('bedrock-budgeteer:feature-flags', {})
        self.assertIn('enable_key_provisioning', feature_flags)


class TestCostAllocationSyncLambdaCode(unittest.TestCase):
    """Test the cost allocation sync Lambda code generation"""

    def test_sync_code_returns_string(self):
        from app.constructs.lambda_functions.cost_allocation_sync import (
            get_cost_allocation_sync_function_code
        )
        code = get_cost_allocation_sync_function_code()
        self.assertIsInstance(code, str)
        self.assertIn('lambda_handler', code)
        self.assertIn('get_cost_and_usage', code)
        self.assertIn('BedrockBudgeteer/CostAllocation', code)

    def test_sync_code_handles_multiple_tags(self):
        from app.constructs.lambda_functions.cost_allocation_sync import (
            get_cost_allocation_sync_function_code
        )
        code = get_cost_allocation_sync_function_code()
        self.assertIn('CostByTeam', code)
        self.assertIn('CostByPurpose', code)
        self.assertIn('CostByTier', code)
        self.assertIn('TotalBedrockCost', code)


class TestCostReconciliationLambdaCode(unittest.TestCase):
    """Test the cost reconciliation Lambda code generation"""

    def test_reconciliation_code_returns_string(self):
        from app.constructs.lambda_functions.cost_reconciliation import (
            get_cost_reconciliation_function_code
        )
        code = get_cost_reconciliation_function_code()
        self.assertIsInstance(code, str)
        self.assertIn('lambda_handler', code)
        self.assertIn('CostReconciliationDrift', code)

    def test_reconciliation_code_has_drift_threshold(self):
        from app.constructs.lambda_functions.cost_reconciliation import (
            get_cost_reconciliation_function_code
        )
        code = get_cost_reconciliation_function_code()
        self.assertIn('DRIFT_THRESHOLD_PERCENT', code)
        self.assertIn('10.0', code)

    def test_reconciliation_code_compares_sources(self):
        from app.constructs.lambda_functions.cost_reconciliation import (
            get_cost_reconciliation_function_code
        )
        code = get_cost_reconciliation_function_code()
        self.assertIn('_get_cost_explorer_total', code)
        self.assertIn('_get_internal_tracking_total', code)
        self.assertIn('_calculate_drift', code)


class TestMonitoringCostAllocationDashboard(unittest.TestCase):
    """Test that monitoring construct has cost allocation dashboard method"""

    def test_monitoring_has_cost_allocation_dashboard_method(self):
        from app.constructs.monitoring import MonitoringConstruct
        self.assertTrue(hasattr(MonitoringConstruct, 'create_cost_allocation_dashboard'))

    def test_dashboard_method_references_correct_namespace(self):
        from app.constructs.monitoring import MonitoringConstruct
        import inspect
        source = inspect.getsource(MonitoringConstruct.create_cost_allocation_dashboard)
        self.assertIn('BedrockBudgeteer/CostAllocation', source)
        self.assertIn('CostByTeam', source)
        self.assertIn('CostByPurpose', source)
        self.assertIn('CostByTier', source)
        self.assertIn('CostReconciliationDrift', source)
        self.assertIn('RogueKeyDetected', source)


if __name__ == '__main__':
    unittest.main()
