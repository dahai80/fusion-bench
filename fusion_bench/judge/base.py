"""Judge abstract base class."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod

from .config import JudgeInput, JudgeVerdict

logger = logging.getLogger(__name__)


class Judge(ABC):
    # Scores model output against criteria. Returns 0-1 score.

    @abstractmethod
    async def judge(self, judge_input: JudgeInput) -> JudgeVerdict: ...
