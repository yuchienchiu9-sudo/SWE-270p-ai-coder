"""Verify dependencies are selected per run, not embedded in every sandbox."""
from pathlib import Path

from project_dependencies import APPROVED_EXTRAS


def test_sandbox_base_and_approved_chart_dependency():
    dockerfile = (Path(__file__).resolve().parents[1] / "Dockerfile.sandbox").read_text()
    assert "streamlit==" in dockerfile
    assert "pytest==" in dockerfile
    assert "matplotlib==" not in dockerfile  # No longer globally required.
    assert APPROVED_EXTRAS["matplotlib"] == "matplotlib==3.10.7"
    assert 'ARG EXTRA_PACKAGES=""' in dockerfile
    assert "pip install -r /workspace/requirements.txt" not in dockerfile
