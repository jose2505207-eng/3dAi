"""Synthetic Module 1 run dirs for offline tests.

Built with cadquery directly and a hand-written run_record.json — NOT via
modules.design, honoring the files-only contract between modules.
"""

import json
from pathlib import Path

import pytest


@pytest.fixture
def make_run_dir(tmp_path):
    def _make(shape, parameters: dict, prompt: str = "test part",
              with_stl: bool = True) -> Path:
        import cadquery as cq
        run_dir = tmp_path / "run"
        run_dir.mkdir(exist_ok=True)
        cq.exporters.export(shape, str(run_dir / "part.step"))
        if with_stl:
            cq.exporters.export(shape, str(run_dir / "part.stl"), tolerance=0.1)
        (run_dir / "run_record.json").write_text(json.dumps({
            "prompt": prompt, "model": "google/gemma-3-27b-it",
            "endpoint": "http://test:8000/v1", "success": True,
            "parameters": parameters,
        }))
        return run_dir
    return _make


@pytest.fixture(autouse=True)
def _clean_material_env(monkeypatch):
    monkeypatch.delenv("MATERIAL", raising=False)
