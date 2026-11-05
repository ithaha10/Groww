"""Groq implementation of the provider-neutral LLM interface."""

from __future__ import annotations

from typing import Any

from src.query.llm.base import LLMClient, LLMResult


class GroqClient(LLMClient):
    def __init__(self, api_key: str | None, model: str | None, temperature: float = 0.1):
        self.api_key = api_key or ""
        self.model = model or ""
        self.temperature = temperature

    def generate(
        self,
        system: str,
        user: str,
        context_chunks: list[dict[str, Any]],
    ) -> LLMResult:
        if not self.api_key:
            return LLMResult("", self.model, error="missing GROQ_API_KEY in .env")
        if not self.model:
            return LLMResult("", self.model, error="missing GROQ_MODEL in .env")

        try:
            from groq import Groq

            client = Groq(api_key=self.api_key)
            response = client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                temperature=self.temperature,
                max_tokens=512,
            )
            text = (response.choices[0].message.content or "").strip()
            return LLMResult(text, self.model)
        except Exception as exc:  # network / auth / bad model id
            return LLMResult("", self.model, error=str(exc))
