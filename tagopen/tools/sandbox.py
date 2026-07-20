"""Resource-limited Python sandbox (no host FS/network by default)."""

from __future__ import annotations

import resource
import sys
from io import StringIO
from typing import Any


def run_python_sandboxed(code: str, timeout_cpu_seconds: int = 2) -> str:
    """Execute Python with dangerous builtins removed and soft CPU limit.

    Note: full process isolation (nsjail/firejail) is preferred for SaaS;
    Contabo uses this in-process sandbox with FS/network builtins stripped.
    """
    safe_builtins: dict[str, Any] = {}
    base = __builtins__ if isinstance(__builtins__, dict) else __builtins__.__dict__  # type: ignore[union-attr]
    for k, v in base.items():
        if k in ("open", "exec", "eval", "__import__", "compile", "input", "breakpoint"):
            continue
        safe_builtins[k] = v

    import datetime
    import json
    import math
    import re

    safe_globals: dict[str, Any] = {
        "__builtins__": safe_builtins,
        "print": print,
        "math": math,
        "json": json,
        "re": re,
        "datetime": datetime,
    }

    old_stdout = sys.stdout
    sys.stdout = buffer = StringIO()
    try:
        try:
            resource.setrlimit(resource.RLIMIT_CPU, (timeout_cpu_seconds, timeout_cpu_seconds + 1))
        except (ValueError, OSError):
            pass
        exec(code, safe_globals)  # noqa: S102
        output = buffer.getvalue()
        return output.strip() or "(no output)"
    except Exception as e:
        return f"Error: {e}"
    finally:
        sys.stdout = old_stdout
