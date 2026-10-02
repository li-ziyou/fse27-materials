import json
import os
from pathlib import Path

import pytest

# For Python 3.10 compatibility, import from exceptiongroup backport
try:
    from exceptiongroup import ExceptionGroup, BaseExceptionGroup
except ImportError:
    # Python 3.11+ has these built-in
    ExceptionGroup = ExceptionGroup  # noqa: F821
    BaseExceptionGroup = BaseExceptionGroup  # noqa: F821

@pytest.fixture(scope="session")
def form_id() -> str:
    configured = os.environ.get("CONTEXTBRANCH_STUDY_FORM_ID")
    if configured:
        return configured
    try:
        return json.loads((Path.cwd() / ".study" / "run.json").read_text(encoding="utf-8")).get("formId", "F1")
    except (OSError, ValueError, TypeError):
        return "F1"


@pytest.fixture
def form_value(form_id: str):
    return lambda f1, f2: f2 if form_id == "F2" else f1


# Make ExceptionGroup and BaseExceptionGroup available globally for tests
import builtins
builtins.ExceptionGroup = ExceptionGroup  
builtins.BaseExceptionGroup = BaseExceptionGroup
