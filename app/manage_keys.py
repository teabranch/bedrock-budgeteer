#!/usr/bin/env python3
"""CLI to manage Bedrock API key provisioning entries in cdk.json.

Usage:
    ./manage_keys.py add --team platform --purpose chatbot-prod --budget-tier medium
    ./manage_keys.py remove --team platform --purpose chatbot-prod
    ./manage_keys.py list

After adding/removing keys, deploy with: cdk deploy
"""
import argparse
import json
import sys
from pathlib import Path

CDK_JSON_PATH = Path(__file__).parent / "cdk.json"
CONFIG_KEY = "bedrock-budgeteer:api-keys"
VALID_TIERS = ("low", "medium", "high")


def load_cdk_json() -> dict:
    with open(CDK_JSON_PATH) as f:
        return json.load(f)


def save_cdk_json(data: dict) -> None:
    with open(CDK_JSON_PATH, "w") as f:
        json.dump(data, f, indent=2)
        f.write("\n")


def get_keys(data: dict) -> list:
    return data.get("context", {}).get(CONFIG_KEY, [])


def set_keys(data: dict, keys: list) -> dict:
    data.setdefault("context", {})[CONFIG_KEY] = keys
    return data


def add_key(args: argparse.Namespace) -> None:
    tier = args.budget_tier
    if tier not in VALID_TIERS:
        print(f"Error: budget-tier must be one of {VALID_TIERS}, got '{tier}'", file=sys.stderr)
        sys.exit(1)

    data = load_cdk_json()
    keys = get_keys(data)

    for entry in keys:
        if entry["team"] == args.team and entry["purpose"] == args.purpose:
            print(f"Key already exists: team={args.team}, purpose={args.purpose} (tier={entry['budget_tier']})")
            print(f"Remove it first if you want to change the tier.")
            sys.exit(1)

    new_entry = {"team": args.team, "purpose": args.purpose, "budget_tier": tier}
    keys.append(new_entry)
    save_cdk_json(set_keys(data, keys))

    print(f"Added: BedrockAPIKey-{args.team}-{args.purpose} (tier={tier})")
    print(f"Run 'cdk deploy' to provision the key.")


def remove_key(args: argparse.Namespace) -> None:
    data = load_cdk_json()
    keys = get_keys(data)
    original_len = len(keys)

    keys = [e for e in keys if not (e["team"] == args.team and e["purpose"] == args.purpose)]

    if len(keys) == original_len:
        print(f"Key not found: team={args.team}, purpose={args.purpose}", file=sys.stderr)
        sys.exit(1)

    save_cdk_json(set_keys(data, keys))
    print(f"Removed: BedrockAPIKey-{args.team}-{args.purpose}")
    print(f"Run 'cdk deploy' to delete the IAM user from CloudFormation.")


def list_keys(args: argparse.Namespace) -> None:
    data = load_cdk_json()
    keys = get_keys(data)

    if not keys:
        print("No API keys configured.")
        return

    print(f"{'IAM User Name':<45} {'Team':<15} {'Purpose':<20} {'Tier':<8}")
    print("-" * 88)
    for entry in keys:
        team = entry["team"]
        purpose = entry["purpose"]
        tier = entry.get("budget_tier", "low")
        print(f"BedrockAPIKey-{team}-{purpose:<26} {team:<15} {purpose:<20} {tier:<8}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Manage Bedrock API key provisioning (updates cdk.json)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="After changes, run 'cdk deploy' to apply.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # add
    add_parser = subparsers.add_parser("add", help="Add a new API key")
    add_parser.add_argument("--team", required=True, help="Team name (e.g., platform, ml-ops)")
    add_parser.add_argument("--purpose", required=True, help="Purpose/use case (e.g., chatbot-prod)")
    add_parser.add_argument("--budget-tier", default="low", choices=VALID_TIERS,
                            help="Budget tier: low=$1, medium=$5, high=$25 (default: low)")
    add_parser.set_defaults(func=add_key)

    # remove
    rm_parser = subparsers.add_parser("remove", help="Remove an API key")
    rm_parser.add_argument("--team", required=True, help="Team name")
    rm_parser.add_argument("--purpose", required=True, help="Purpose/use case")
    rm_parser.set_defaults(func=remove_key)

    # list
    list_parser = subparsers.add_parser("list", help="List all configured API keys")
    list_parser.set_defaults(func=list_keys)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
