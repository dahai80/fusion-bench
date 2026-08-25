"""Identity model + resolution middleware for API authentication."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from .rbac import Role

logger = logging.getLogger(__name__)


@dataclass
class Identity:
    user_id: str
    workspace_id: str = "default"
    role: Role = Role.VIEWER
    source: str = "anonymous"
    scopes: list[str] = field(default_factory=list)

    @property
    def is_anonymous(self) -> bool:
        return self.source == "anonymous"
