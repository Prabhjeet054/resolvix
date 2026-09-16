"""
Streamlit entry point for Resolvix Agentic RAG.

Delegates to demo_app (health badges, dual-mode search, Ollama agent UI).
"""

from __future__ import annotations

import sys
from pathlib import Path

_APP_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _APP_DIR.parent
for path in (_PROJECT_ROOT, _APP_DIR):
    path_str = str(path)
    if path_str not in sys.path:
        sys.path.insert(0, path_str)

from demo_app import main

main()
