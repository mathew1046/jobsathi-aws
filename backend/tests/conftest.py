# tests/conftest.py
# pytest configuration for the JobSathi backend test suite

import pytest


def pytest_configure(config):
    """Register custom markers so pytest doesn't warn about unknown marks."""
    config.addinivalue_line(
        "markers",
        "integration: marks tests that require a real database and AWS credentials",
    )
