"""Shared test fixtures for Richmond Common."""
import sys
from pathlib import Path

import pytest

# Add src/ and tests/ to Python path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent))

from factories import make_escribemeetings_raw  # noqa: E402


@pytest.fixture
def escribemeetings_samples():
    """Two sample eSCRIBE meetings in real API response format."""
    return [
        make_escribemeetings_raw(date="2026/03/03", guid="abc-001"),
        make_escribemeetings_raw(date="2026/03/10", guid="def-002"),
    ]
