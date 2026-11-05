"""Provider-neutral LLM interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass
class LLMResult:
    answer_text: str
    model: str
    error: str | None = None


class LLMClient(ABC):
    @abstractmethod
    def generate(
        self,
        system: str,
        user: str,
        context_chunks: list[dict[str, Any]],
    ) -> LLMResult:
        ...
