"""Tag extraction — regex isolation of <thinking>/<dsl>/<visual_state> blocks.

Tags are expected to appear verbatim in model output. All extractors are
non-greedy DOTALL so they capture the inner content without crossing tag
boundaries. Returns None when the tag is absent.
"""

from __future__ import annotations

import re

_THINKING_RE = re.compile(r"<thinking>\n?(.*?)\n?</thinking>", re.DOTALL)
_DSL_RE = re.compile(r"<dsl>\n?(.*?)\n?</dsl>", re.DOTALL)
_VISUAL_RE = re.compile(r"<visual_state>\n?(.*?)\n?</visual_state>", re.DOTALL)


def extract_thinking(text: str) -> str | None:
    if not isinstance(text, str):
        return None
    m = _THINKING_RE.search(text)
    return m.group(1).strip() if m else None


def extract_dsl(text: str) -> str | None:
    if not isinstance(text, str):
        return None
    m = _DSL_RE.search(text)
    return m.group(1).strip() if m else None


def extract_visual_state(text: str) -> str | None:
    if not isinstance(text, str):
        return None
    m = _VISUAL_RE.search(text)
    return m.group(1).strip() if m else None


def extract_visual_type(dsl_dict: dict) -> str | None:
    # Pull meta.visual_type from a parsed DSL dict (v3.0 schema top-level field).
    if not isinstance(dsl_dict, dict):
        return None
    meta = dsl_dict.get("meta")
    if not isinstance(meta, dict):
        return None
    vt = meta.get("visual_type")
    return str(vt) if vt else None
