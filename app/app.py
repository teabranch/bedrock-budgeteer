#!/usr/bin/env python3
"""
Bedrock Budgeteer CDK Application Entry Point

Reads configuration from budgeteer.config.yaml (or a custom path via --context config=path).
All user-facing settings live in that YAML file — cdk.json is reserved for CDK framework flags.
"""
import os
import sys
from pathlib import Path

import yaml
import aws_cdk as cdk

from app.app_stack import BedrockBudgeteerStack

DEFAULT_CONFIG_FILE = "budgeteer.config.yaml"


def load_config(app: cdk.App) -> dict:
    """Load configuration from YAML file.

    Resolution order:
      1. --context config=<path>  (explicit override)
      2. budgeteer.config.yaml in the app directory (default)
    """
    config_path = app.node.try_get_context("config") or DEFAULT_CONFIG_FILE

    path = Path(config_path)
    if not path.is_absolute():
        path = Path(__file__).parent / path

    if not path.exists():
        print(f"Error: config file not found: {path}", file=sys.stderr)
        print(f"Create {DEFAULT_CONFIG_FILE} or pass --context config=<path>", file=sys.stderr)
        sys.exit(1)

    with open(path) as f:
        config = yaml.safe_load(f)

    return config or {}


def inject_context(app: cdk.App, config: dict) -> None:
    """Map YAML config into the CDK context keys that constructs already expect."""
    features = config.get("features", {})
    infra = config.get("infrastructure", {})

    # Feature flags — merge features + infrastructure into the existing context key
    feature_flags = {
        "enable_agentcore_budgeting": features.get("enable_agentcore_budgeting", False),
        "enable_key_provisioning": features.get("enable_key_provisioning", False),
        "enable_cost_allocation_reporting": features.get("enable_cost_allocation_reporting", False),
        "enable-encryption": infra.get("enable_encryption", True),
        "enable-point-in-time-recovery": infra.get("enable_point_in_time_recovery", True),
        "enable-multi-az": infra.get("enable_multi_az", False),
        "skip-s3-public-access-block": infra.get("skip_s3_public_access_block", False),
    }
    app.node.set_context("bedrock-budgeteer:feature-flags", feature_flags)

    # Config block — used by app_stack for alert-email and budget-limits
    budgets = config.get("budgets", {})
    app.node.set_context("bedrock-budgeteer:config", {
        "region": config.get("region", "us-east-1"),
        "alert-email": config.get("alert_email", ""),
        "budget-limits": {
            "default-user-budget": budgets.get("default_user_budget_usd", 1),
            "max-user-budget": budgets.get("default_user_budget_usd", 1) * 3,
        },
        "retention": {
            "logs": config.get("retention", {}).get("log_retention_days", 7),
        },
    })

    # Pass full config sections for ConfigurationConstruct to read SSM defaults
    app.node.set_context("bedrock-budgeteer:budgets", budgets)
    app.node.set_context("bedrock-budgeteer:key-provisioning", config.get("key_provisioning", {}))
    app.node.set_context("bedrock-budgeteer:agentcore", config.get("agentcore", {}))
    app.node.set_context("bedrock-budgeteer:retention", config.get("retention", {}))


# Single environment configuration with us-east-1 default
environment_config = cdk.Environment(
    account=os.getenv('CDK_DEFAULT_ACCOUNT'),
    region=os.getenv('CDK_DEFAULT_REGION', 'us-east-1')
)


def main():
    """Main application entry point"""
    app = cdk.App()

    config = load_config(app)
    inject_context(app, config)

    environment_name = "production"

    BedrockBudgeteerStack(
        app,
        "BedrockBudgeteer",
        environment_name=environment_name,
        env=environment_config,
        description="Bedrock Budgeteer serverless budget monitoring system"
    )

    app.synth()


if __name__ == "__main__":
    main()
