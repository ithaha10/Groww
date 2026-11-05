"""Query orchestrator: guardrails -> retrieve -> evidence -> generate/refuse."""

from __future__ import annotations

from typing import Any

from src.config import get_config
from src.query.generate import generate_answer, refusal_payload
from src.query.guardrails import SEBI_LINK, check_question
from src.query.retrieve import new_query_id, retrieve


def answer_question(question: str, config: dict | None = None) -> dict[str, Any]:
    config = config or get_config()
    question = (question or "").strip()
    if not question:
        return {
            "query_id": None,
            "query": "",
            "mode": "refuse",
            "intent": "empty",
            "answer_text": "Please enter a scheme-fact question.",
            "citation_url": SEBI_LINK,
            "last_updated": None,
            "guardrail": "empty",
            "error": None,
        }

    guard = check_question(question)

    if guard.pii:
        # Never persist a question that contains personal identifiers.
        return {
            "query_id": None,
            "query": "",
            "mode": "refuse",
            "intent": "pii",
            "answer_text": guard.message,
            "citation_url": guard.url,
            "last_updated": None,
            "guardrail": "pii",
            "error": None,
            "persisted": False,
        }

    query_id = new_query_id()

    if guard.blocked:
        payload = refusal_payload(
            config,
            question,
            query_id,
            reason=guard.reason or guard.intent,
            message=guard.message,
            url=guard.url,
        )
        payload["guardrail"] = guard.intent
        return payload

    try:
        retrieval = retrieve(config, question, query_id=query_id)
    except Exception as exc:
        return {
            "query_id": query_id,
            "query": question,
            "mode": "error",
            "intent": guard.intent,
            "answer_text": "",
            "citation_url": SEBI_LINK,
            "last_updated": None,
            "guardrail": "ok",
            "error": str(exc),
        }

    payload = generate_answer(config, question, retrieval, query_id)
    payload["guardrail"] = "ok"
    payload["retrieval_hits"] = len(retrieval.get("hits") or [])
    return payload
