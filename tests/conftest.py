"""Shared pytest fixtures."""

import pytest

from source.flow.execution import orchestrator


@pytest.fixture(autouse=True)
def isolate_chart_output(tmp_path, monkeypatch):
    """Send default Gantt charts to a temp dir so tests never rewrite results/."""
    monkeypatch.setattr(orchestrator, "DEFAULT_CHART_DIR", tmp_path / "charts")
