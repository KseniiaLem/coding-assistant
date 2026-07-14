"""Small shared helpers."""

import os


def get_env(key: str) -> str:
    """Return the environment variable, failing loudly if it is not set."""
    result = os.getenv(key)
    if result is None:
        raise ValueError(f"Environment variable {key} not set")
    return result
