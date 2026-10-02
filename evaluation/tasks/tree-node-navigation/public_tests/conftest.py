import json
import os
from pathlib import Path

import pytest

# Monkey-patch typing.Self for Python 3.10 compatibility
import sys
import typing
try:
    from typing import Self
except ImportError:
    from typing_extensions import Self
    typing.Self = Self

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
