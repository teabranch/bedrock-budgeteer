#!/usr/bin/env python3
"""
Bedrock Budgeteer CDK Application Entry Point
"""
import os
import aws_cdk as cdk

from app.app_stack import BedrockBudgeteerStack


# Single environment configuration with us-east-1 default
# Users can override region via CDK_DEFAULT_REGION environment variable
environment_config = cdk.Environment(
    account=os.getenv('CDK_DEFAULT_ACCOUNT'),
    region=os.getenv('CDK_DEFAULT_REGION', 'us-east-1')
)

def main():
    """Main application entry point"""
    app = cdk.App()
    
    # Single deployment without environment separation
    environment_name = "production"
    
    # Create the stack
    BedrockBudgeteerStack(
        app, 
        "BedrockBudgeteer",
        environment_name=environment_name,
        env=environment_config,
        description="Bedrock Budgeteer serverless budget monitoring system"
    )
    
    # Tags are handled by the TaggingFramework in the stack
    
    app.synth()


if __name__ == "__main__":
    main()
