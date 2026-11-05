# Product Requirements Document

**Product:** Groww Mutual Fund FAQ Assistant  
**Type:** Working prototype (small-corpus RAG)  
**Source brief:** Problem Statement  
**Status:** Draft for build  
**Last updated:** 2026-11-01

---

## 1. Summary

Build a small, facts-only FAQ assistant that answers questions about selected HDFC Mutual Fund schemes using official public pages only. Every answer must include one source link. The assistant must never give investment advice.

This is a **RAG demo**. Each pipeline stage must persist its output so the flow can be inspected: load → chunk → embed → store → retrieve → generate.

---

## 2. Problem

Retail users and support/content teams need fast, cited facts about mutual fund schemes (expense ratio, exit load, minimum SIP, ELSS lock-in, riskometer, benchmark, statement download). Today those facts sit on public pages and are re-answered manually. Opinionated “should I buy/sell?” questions must be refused.

---

## 3. Goals and non-goals

### Goals

- Answer factual scheme/AMC questions from a small official corpus.
- Show **one clear citation URL** on every answer.
- Refuse advice, portfolio, and performance-comparison questions politely.
- Make the RAG pipeline inspectable: store artifacts after each stage.
- Keep ingestion and retrieval settings in config; keep model/API keys in `.env`.

### Non-goals

- Investment advice, suitability, or “best fund” ranking.
- Computing or comparing returns (direct users to the official factsheet).
- Login, account data, or any PII collection.
- Scraping app backends or third-party blogs.
- Full Groww product coverage (only the listed AMC + four schemes).

---

## 4. Users

| User | Need |
| --- | --- |
| Retail investor comparing schemes | Fast, cited facts before they open full pages |
| Support / content team | Repeatable answers to the same MF FAQs |

---

## 5. In-scope corpus

Scrape and store **only** these official public Groww pages (and any official factsheet / AMFI / SEBI / AMC pages linked from them that are required to answer in-scope FAQs). Target **15–25 source URLs** in the submitted source list.

| # | Entity | URL |
| --- | --- | --- |
| 1 | AMC overview — HDFC Mutual Fund | https://groww.in/mutual-funds/amc/hdfc-mutual-funds |
| 2 | Large Cap — HDFC Large Cap Fund Direct Growth | https://groww.in/mutual-funds/hdfc-large-cap-fund-direct-growth |
| 3 | Flexi Cap — HDFC Flexi Cap Direct Plan Growth | https://groww.in/mutual-funds/hdfc-equity-fund-direct-growth |
| 4 | ELSS — HDFC ELSS Tax Saver Fund Direct Plan Growth | https://groww.in/mutual-funds/hdfc-elss-tax-saver-fund-direct-plan-growth |
| 5 | Mid Cap — HDFC Mid Cap Fund Direct Growth | https://groww.in/mutual-funds/hdfc-mid-cap-fund-direct-growth |

**Allowed source types:** Groww public scheme/AMC pages, official AMC factsheets, AMFI, SEBI investor-education pages.  
**Disallowed:** App backend screenshots, unofficial blogs, forums, news roundups.

---

## 6. Functional requirements

### 6.1 Question types to answer

Answer only when the fact is in the corpus:

- Expense ratio
- Exit load
- Minimum SIP / minimum investment
- ELSS lock-in
- Riskometer
- Benchmark
- How to download capital-gains / account statements (procedure from official public help pages)

### 6.2 Answer format

Every successful answer must:

1. Identify the **exact fact** asked (scheme + field).
2. State the fact in **≤ 3 sentences**.
3. Include **one citation link**.
4. Include **Last updated from sources: &lt;date or scrape timestamp&gt;**.
5. Stay factual (no “you should”, no return claims).

### 6.3 Refusal policy

Refuse (polite, facts-only message + one relevant **educational** official link) when the user asks:

- Buy / sell / hold / switch advice
- Portfolio construction or “which fund is better”
- Return prediction, ranking, or computed performance comparison
- Anything requiring PII or account access

If the fact is missing from the corpus, say so and point to the most relevant official page rather than guessing.

### 6.4 PII

Do not accept or store PAN, Aadhaar, account numbers, OTPs, emails, or phone numbers. If the user pastes them, do not persist them; respond that personal identifiers are not needed for this FAQ tool.

### 6.5 UI (tiny prototype)

- Welcome line
- **3 example questions**
- Persistent note: **“Facts-only. No investment advice.”**
- Chat or Q&A input
- Answer area with citation + last-updated line
- Disclaimer snippet (same facts-only language) visible in the UI

Optional for the RAG demo (strongly preferred): a simple way to inspect stage artifacts (loaded docs, chunks, embeddings metadata, retrieved chunks).

---

## 7. Technical requirements (phased RAG)

Implement in phases. Persist each stage’s output so it can be shown in the demo.

### Phase 1 — Data loading

- Fetch the in-scope public pages.
- Normalize into stored documents (raw HTML/text + URL + fetch timestamp).
- Output artifact: loaded corpus (files or table keyed by URL).

### Phase 2 — Data chunking

- Choose a chunking strategy that fits scheme-page structure (headings, fact tables, FAQ blocks). The coding agent may pick the strategy; it must be documented and configurable.
- Output artifact: chunks with `source_url`, `scheme/amc id`, `chunk_id`, text.

### Phase 3 — Embedding

- Model: `sentence-transformers/all-MiniLM-L6-v2`
- Output artifact: embeddings aligned to chunk IDs.

### Phase 4 — Vector store

- Database: **ChromaDB**
- Persist collection locally for the demo.

### Phase 5 — Retrieval

- Query embedding: **same model as ingestion**
- Vector DB: **same Chroma collection as ingestion**
- Return top-k chunks with source URLs for citation.

### Phase 6 — Generation (LLM)

- Primary path: **Groq**
- Model name and API keys from **`.env`** (do not hardcode).
- Default model to configure: `qwen/qwen3-32b` (confirm exact Groq model id at implementation; Problem Statement lists `qwen/qwen3.8-27b` — resolve to a valid Groq model in config).
- Design config so **Gemini, OpenAI, Anthropic, Mistral** can be swapped later (provider + model id), even if only Groq is wired in the prototype.

### Config vs secrets

| Item | Location |
| --- | --- |
| Chunking strategy / size / overlap | Config file |
| Embedding model name | Config file |
| Chroma path / collection name | Config file |
| Retrieval top-k | Config file |
| LLM provider + model id | Config + `.env` for keys |
| Source URL list | Config or data file |
| Groq / Gemini / OpenAI / Anthropic / Mistral API keys | `.env` only |

---

## 8. Skills the prototype must demonstrate

| ID | Skill | Product implication |
| --- | --- | --- |
| W1 | Thinking like a model | Parse the exact fact; answer vs refuse |
| W2 | LLMs & prompting | Concise answers, polite refusals, citation wording |
| W3 | RAG only | Small-corpus retrieval with accurate AMC/SEBI/AMFI/Groww public citations |

---

## 9. Deliverables

1. **Working prototype** (hosted app/notebook) **or** a ≤ 3-minute demo video if hosting is not possible.
2. **Source list** (CSV or Markdown) of the **15–25 URLs** used.
3. **README** with setup steps, scope (AMC + schemes), and known limits.
4. **Sample Q&A file** (5–10 queries) with the assistant’s answers and links.
5. **Disclaimer snippet** used in the UI (facts-only, no advice).
6. **Stage artifacts** from the RAG pipeline (for demo inspection).

---

## 10. Success criteria

- In-scope fact questions return a correct value grounded in a retrieved chunk, with a working official URL.
- Advice / performance questions are refused with an educational official link; no invented numbers.
- Every answer is ≤ 3 sentences and includes last-updated + one citation.
- UI shows welcome, 3 examples, and the facts-only note.
- Changing embedding model, Chroma settings, or LLM model is possible via config / `.env` without code rewrite.
- A reviewer can inspect load → chunk → embed → retrieve outputs independently.

---

## 11. Risks and known limits (to document in README)

- Groww page layout changes can break scraping.
- Scheme facts (expense ratio, exit load) change; answers are only as fresh as the last scrape.
- Tiny corpus: questions about other AMCs/schemes must be declined or redirected.
- LLM may hallucinate if retrieval is weak; prompts must require “only use retrieved text” and refuse when evidence is missing.
- Groq model id in the brief may not match the live catalog; lock a valid id in `.env`.

---

## 12. Out-of-scope follow-ups (not this prototype)

- Multi-AMC coverage
- Live authenticated statement download
- Return calculators
- Voice / mobile-native app
- Production auth, rate limits, and monitoring beyond a demo

---

## 13. Suggested first example questions (UI)

1. What is the expense ratio of HDFC Large Cap Fund Direct Growth?
2. What is the lock-in for HDFC ELSS Tax Saver Fund Direct Plan Growth?
3. How do I download a capital-gains statement?

---

## 14. Disclaimer (required in UI)

Use a short snippet equivalent to:

> This assistant shares publicly available scheme facts only. It is not investment advice. It does not recommend buying, selling, or holding any fund. Always verify details on the official scheme page or factsheet.
