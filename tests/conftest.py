import os
import sys
from pathlib import Path
import pytest

print(str(Path(__file__).parents[1]))
sys.path.append(str(Path(__file__).parents[1]))


def environment_check() -> bool:
    if any(os.getenv(key) for key in ["OPENAI_API_KEY", "ANTHROPIC_API_KEY"]):
        return True
    return False

def pytest_sessionstart(session: pytest.Session) -> None:
    """Session start hook."""
    if not environment_check():
        pytest.exit("Skipping tests due to missing environment variables")
