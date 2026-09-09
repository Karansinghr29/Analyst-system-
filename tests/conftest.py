import os
import sys

BASE = r"D:\data science\AI Analytics System"
if BASE not in sys.path:
    sys.path.insert(0, BASE)

import pytest  # noqa: E402

from engine.semantic_registry import SemanticRegistry  # noqa: E402
from engine.execution import MetricExecutor  # noqa: E402
from engine.validation import ValidationIndex  # noqa: E402


@pytest.fixture(scope="session")
def registry():
    return SemanticRegistry()


@pytest.fixture(scope="session")
def validation_index():
    return ValidationIndex()


@pytest.fixture(scope="session")
def executor(registry, validation_index):
    return MetricExecutor(registry, validation_index)
