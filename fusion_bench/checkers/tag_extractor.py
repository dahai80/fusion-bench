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
