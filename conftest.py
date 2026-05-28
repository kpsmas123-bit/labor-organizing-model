"""
Project-root conftest.py — makes `pipeline` importable when running pytest
from any working directory.
"""
import sys
from pathlib import Path

# Insert the project root at the front of sys.path so `from pipeline.xxx import …`
# resolves correctly regardless of how pytest is invoked (e.g. `pytest tests/`).
sys.path.insert(0, str(Path(__file__).parent))
