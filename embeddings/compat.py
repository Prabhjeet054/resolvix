"""
Compatibility and environment shim for Resolvix.

Handles Windows Smart App Control (SAC) / AppLocker environments where
compiled C-extension DLLs (such as _regex.pyd or sklearn's _cyutility.pyd)
may be restricted by enterprise code integrity policies.
"""

from __future__ import annotations

import importlib.machinery
import re
import sys
import types


def apply_compat_shims() -> None:
    """Apply shims for regex and sklearn if native modules cannot load."""
    # 1. Regex shim
    if "regex" not in sys.modules:
        try:
            import regex  # noqa: F401
        except Exception:
            sys.modules["regex"] = re

    # 2. Sklearn shim (sentence-transformers only needs light evaluation metrics)
    if "sklearn" not in sys.modules:
        try:
            import sklearn  # noqa: F401
        except Exception:
            mock_metrics = types.ModuleType("sklearn.metrics")
            mock_metrics.__spec__ = importlib.machinery.ModuleSpec("sklearn.metrics", None)
            for attr in [
                "pairwise_distances",
                "roc_curve",
                "f1_score",
                "matthews_corrcoef",
                "precision_score",
                "recall_score",
                "accuracy_score",
            ]:
                setattr(mock_metrics, attr, lambda *args, **kwargs: 0.0)

            mock_sklearn = types.ModuleType("sklearn")
            mock_sklearn.__spec__ = importlib.machinery.ModuleSpec("sklearn", None)
            mock_sklearn.__path__ = []

            mock_base = types.ModuleType("sklearn.base")
            mock_base.__spec__ = importlib.machinery.ModuleSpec("sklearn.base", None)
            mock_base.clone = lambda x: x

            mock_sklearn.metrics = mock_metrics
            mock_sklearn.base = mock_base

            sys.modules["sklearn"] = mock_sklearn
            sys.modules["sklearn.metrics"] = mock_metrics
            sys.modules["sklearn.base"] = mock_base

    # 3. Transformers sklearn flag
    try:
        import transformers.utils.import_utils as _t_iu

        _t_iu.is_sklearn_available = lambda: False
    except Exception:
        pass


apply_compat_shims()
