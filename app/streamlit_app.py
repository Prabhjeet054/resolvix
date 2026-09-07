"""
Streamlit entry point for the Multilingual Support Ticket Assistant.

Delegates to demo_app, which provides the two-column query/results UI
(sample queries, hybrid category/priority filters, confidence cards).
"""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure both project root and app/ are importable when launched via Streamlit.
_APP_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _APP_DIR.parent
for path in (_PROJECT_ROOT, _APP_DIR):
    path_str = str(path)
    if path_str not in sys.path:
        sys.path.insert(0, path_str)

from demo_app import main

main()
