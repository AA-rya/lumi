"""Environment configuration validation for Lumi Lambda function.

This module provides environment variable validation and configuration
management for the Lumi Lambda handler. Call validate_environment() at
startup to catch missing configuration early.

Usage:
    from config import validate_environment
    validate_environment()  # Raises EnvironmentError if missing required vars
"""
import os
import sys

REQUIRED_ENV_VARS = [
    'GOOGLE_CLIENT_ID',
    'GOOGLE_CLIENT_SECRET',
    'BEDROCK_API_KEY',
]

OPTIONAL_ENV_VARS = {
    'BEDROCK_REGION': 'us-east-1',
    'DYNAMO_REGION': 'us-east-2',
    'DYNAMO_CONVERSATIONS_TABLE': 'Lumi_convos_v2',
    'DYNAMO_USERS_TABLE': 'Lumi_users',
    'DYNAMO_RETIREMENT_TABLE': 'Lumi_retirement',
}


def validate_environment():
    """Validate that all required environment variables are set.

    This function checks that critical environment variables are present
    before the Lambda handler starts processing requests. This catches
    deployment configuration errors immediately rather than failing
    cryptically during user requests.

    Raises:
        EnvironmentError: If any required environment variable is missing.
                         Error message lists all missing variables.

    Returns:
        bool: True if validation passes (never reaches here on failure).
    """
    missing = []
    for var in REQUIRED_ENV_VARS:
        if not os.environ.get(var):
            missing.append(var)

    if missing:
        error_msg = f"Missing required environment variables: {', '.join(missing)}"
        print(f"ERROR: {error_msg}", file=sys.stderr)
        print(f"See .env.example for required configuration", file=sys.stderr)
        raise EnvironmentError(error_msg)

    return True


def get_env(key, default=None):
    """Get an environment variable with optional default value.

    Args:
        key (str): Environment variable name.
        default (str, optional): Default value if key not found. Defaults to None.

    Returns:
        str: Environment variable value or default.
    """
    return os.environ.get(key, default)


def get_required_env(key):
    """Get a required environment variable.

    Args:
        key (str): Environment variable name.

    Returns:
        str: Environment variable value.

    Raises:
        ValueError: If the variable is not set.
    """
    value = os.environ.get(key)
    if not value:
        raise ValueError(f"Required environment variable not set: {key}")
    return value
