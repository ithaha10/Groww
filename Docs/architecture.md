# Architecture

**Product:** Groww Mutual Fund FAQ Assistant  
**Based on:** [prd.md](./prd.md)  
**Style:** Small-corpus RAG prototype with inspectable stages  
**Last updated:** 2026-11-01

---

## 1. Design intent

A local, phase-wise RAG system that:

1. Loads a fixed set of official public pages.
2. Persists **every stage output** (load → chunk → embed → store → retrieve → generate) so a reviewer can inspect the demo.
3. Answers only scheme/AMC facts with **one citation**.
4. Refuses advice, performance math, and PII before generation when possible.
5. Reads tunables from a **config file** and secrets from **`.env`**.

No accounts, no backends, no third-party blogs.

---

## 2. High-level system

Two runtimes share one corpus and one embedding model:

| Runtime | When | Path |
| --- | --- | --- |
| **Ingestion** | Offline / on demand | URLs → documents → chunks → embeddings → Chroma |
| **Query** | Per user question | Guardrails → embed query → retrieve → (optional) generate → formatted answer |

```text
                    config.yaml + .env
                            |
        +-------------------+-------------------+
        |                                       |
   [Ingestion CLI]                        [Query app]
        |                                       |
        v                                       v
   Public pages                          User question
        |                                       |
        v                                       v
   data/raw/  (Phase 1)              PII + intent gate
        |                                       |
        v                                       v
   data/chunks/ (Phase 2)            Query embedding
        |                            (same MiniLM)
        v                                       |
   embeddings + Chroma (3–4)                    v
        |                            Chroma top-k
        +----------------------------> retrieved/
                                        |
                                        v
                                   Groq (or stub)
                                        |
                                        v
                                   Answer + 1 URL
                                   + last-updated
```

---

## 3. Component map

| Component | Responsibility |
| --- | --- |
| **Source catalog** | 5 seed Groww URLs + extra official pages (factsheet, AMFI, SEBI, help) totaling 15–25 URLs |
| **Loader** | HTTP fetch, extract main text, record `fetched_at`, write raw artifacts |
| **Chunker** | Split by page structure (headings / fact tables / FAQ blocks); attach metadata |
| **Embedder** | `sentence-transformers/all-MiniLM-L6-v2` for chunks **and** queries |
| **Vector store** | Persistent ChromaDB collection |
| **Guardrails** | PII strip/refuse; advice / returns / out-of-scope intent |
| **Retriever** | Embed query, `top_k` from same collection, return chunks + URLs |
| **LLM adapter** | Provider interface; prototype implements **Groq**; stubs for Gemini, OpenAI, Anthropic, Mistral |
| **Prompt layer** | Facts-only system prompt; answer vs refuse; citation wording |
| **UI** | Welcome, 3 examples, disclaimer, Q&A, citation, last-updated; optional artifact viewer |
| **Config / env** | All knobs in config; keys and live model id in `.env` |

---

## 4. Phased pipeline and artifacts

Each phase writes files (JSON/JSONL preferred) under `data/`. Do not overwrite silently; version by run timestamp or keep `latest/` plus dated folders.

### Phase 1 — Data loading

**Input:** `config.sources` (seed URLs + allowlist of official domains).

**Process:**

- Fetch each URL.
- Store raw HTML and extracted plaintext.
- Record metadata: `url`, `title`, `entity_id` (amc / scheme), `fetched_at`, `http_status`, `content_hash`.

**Artifact:** `data/raw/documents.jsonl`

```json
{
  "doc_id": "hdfc-large-cap",
  "url": "https://groww.in/mutual-funds/hdfc-large-cap-fund-direct-growth",
  "entity_type": "scheme",
  "entity_id": "hdfc-large-cap-direct-growth",
  "title": "...",
  "text": "...",
  "html_path": "data/raw/html/hdfc-large-cap.html",
  "fetched_at": "2026-11-01T10:00:00Z"
}
```

**Constraint:** Only Groww public pages and official AMC / AMFI / SEBI / factsheet / help pages.

### Phase 2 — Data chunking

**Strategy (default, configurable):** structure-aware recursive split.

1. Split on headings (`h1`–`h3`) and labeled fact rows (Expense ratio, Exit load, Min SIP, Riskometer, Benchmark, Lock-in).
2. If a section is still large, recursive character split with overlap.
3. Keep fact-table rows as **atomic chunks** so a single field does not split across vectors.

**Config knobs:** `chunk_strategy`, `chunk_size`, `chunk_overlap`, `min_chunk_chars`.

**Artifact:** `data/chunks/chunks.jsonl`

```json
{
  "chunk_id": "hdfc-large-cap::expense-ratio",
  "doc_id": "hdfc-large-cap",
  "entity_id": "hdfc-large-cap-direct-growth",
  "source_url": "https://groww.in/mutual-funds/hdfc-large-cap-fund-direct-growth",
  "section": "expense_ratio",
  "text": "Expense ratio: ...",
  "fetched_at": "2026-11-01T10:00:00Z"
}
```

### Phase 3 — Embedding

**Model:** `sentence-transformers/all-MiniLM-L6-v2` (name from config).

**Process:** Embed `chunk.text`; store vector id = `chunk_id`.

**Artifact:** `data/embeddings/embeddings.jsonl` (id + dim + optional vector dump for demo) plus metadata sidecar without full vectors if files get large.

### Phase 4 — Vector store

**Store:** ChromaDB, on-disk persist path from config.

**Collection metadata per item:** `chunk_id`, `doc_id`, `entity_id`, `source_url`, `section`, `fetched_at`, `text`.

**Artifact:** `data/chroma/` (persist dir) + `data/chroma/collection_info.json` (name, count, embedding model).

Ingestion and query **must** use the same collection and the same embedding model.

### Phase 5 — Retrieval

**Input:** Guardrail-passed user question.

**Process:**

1. Embed question with the ingestion model.
2. Query Chroma `top_k` (config).
3. Optionally filter by detected `entity_id` if the question names a scheme.
4. Write retrieved set before calling the LLM.

**Artifact:** `data/retrieved/{query_id}.json`

```json
{
  "query": "What is the expense ratio of HDFC Large Cap Fund Direct Growth?",
  "query_id": "...",
  "top_k": 5,
  "hits": [
    {
      "chunk_id": "...",
      "score": 0.82,
      "source_url": "...",
      "text": "...",
      "fetched_at": "..."
    }
  ]
}
```

**Citation rule:** The answer’s **single** link is the `source_url` of the highest-scoring hit that actually contains the fact. If none do, skip generation and refuse with the best official page URL.

### Phase 6 — Generation

**Primary provider:** Groq.  
**Model id:** from `.env` (validate against Groq catalog at implement time; brief name may differ).

**Inputs to the LLM:**

- System prompt (facts-only, ≤3 sentences, one URL, last-updated, no advice).
- User question.
- Retrieved chunk texts + URLs + `fetched_at`.

**Outputs:**

- `answer_text`
- `citation_url`
- `last_updated` (max `fetched_at` among used chunks)
- `mode`: `answer` | `refuse`

**Artifact:** `data/generated/{query_id}.json`

**Provider adapter (interface):**

```text
LLMClient.generate(system, user, context_chunks) -> LLMResult
```

| Provider | Prototype |
| --- | --- |
| Groq | Implemented |
| Gemini / OpenAI / Anthropic / Mistral | Interface + config keys only |

Switching providers is `llm.provider` + env key, not a rewrite of retrieval.

---

## 5. Query-time control flow

```text
User question
    │
    ├─ PII detected? ──yes──► Refuse: identifiers not needed; do not store the message
    │
    ├─ Advice / compare / returns / other AMC? ──yes──► Template refuse
    │         + one educational official link (SEBI/AMFI/Groww help)
    │
    ├─ Statement-download how-to? ──► Retrieve help/official chunks only
    │
    └─ Fact question
            │
            Embed → Chroma top_k
            │
            Evidence sufficient?
               ├─ no  → Refuse: fact not in corpus + relevant official URL
               └─ yes → LLM grounded on chunks only
                          → UI: ≤3 sentences, 1 link, last-updated
```

Guardrails run **before** retrieval for PII and clear advice. Ambiguous questions may retrieve first, then refuse if chunks are irrelevant.

---

## 6. Prompt contract (generation)

System instructions must enforce:

- Use **only** provided chunks. If the fact is absent, say so; do not invent numbers.
- Identify scheme + field in the first sentence when answering.
- **≤ 3 sentences.**
- No “should buy/sell/hold”, no return claims, no rankings.
- Emit exactly one source URL from the provided list.
- Include `Last updated from sources: <ISO date from chunk metadata>`.

Refusal template (no LLM required, or LLM with a refuse mode):

> I can only share publicly available scheme facts, not investment advice. For investor education, see &lt;official link&gt;.

---

## 7. UI architecture

Single-page prototype (Streamlit or equivalent is enough).

**Always visible:**

- Welcome line
- Three example questions (from PRD §13)
- Note: **Facts-only. No investment advice.**
- Disclaimer (PRD §14)

**Main pane:** question input → answer, citation URL, last-updated.

**Demo pane (preferred):** tabs or expander for latest run of raw docs, chunks, retrieval hits, generated payload. Read from `data/` artifacts; do not hide the RAG stages.

No login. Do not log raw user text that matches PII patterns.

---

## 8. Configuration

### `config.yaml` (checked in)

```yaml
sources:
  - id: hdfc-amc
    url: https://groww.in/mutual-funds/amc/hdfc-mutual-funds
    entity_type: amc
  # ... four schemes ...

allowed_domains:
  - groww.in
  - www.hdfcfund.com
  - www.amfiindia.com
  - www.sebi.gov.in

chunking:
  strategy: structure_recursive
  chunk_size: 512
  chunk_overlap: 64
  min_chunk_chars: 40

embedding:
  model: sentence-transformers/all-MiniLM-L6-v2

chroma:
  persist_dir: data/chroma
  collection: groww_mf_faq

retrieval:
  top_k: 5

llm:
  provider: groq          # groq | gemini | openai | anthropic | mistral
  # model id lives in .env so catalog changes do not require code edits
```

### `.env` (not committed)

```text
GROQ_API_KEY=
GROQ_MODEL=               # valid Groq id, e.g. qwen/qwen3-32b once confirmed
GEMINI_API_KEY=
OPENAI_API_KEY=
ANTHROPIC_API_KEY=
MISTRAL_API_KEY=
```

Query embedding model **must** equal `embedding.model`. Vector DB **must** equal `chroma.collection`.

---

## 9. Suggested repository layout

```text
config.yaml
.env.example
README.md
Docs/
  prd.md
  architecture.md
  Problem Statement
src/
  ingest/
    load.py
    chunk.py
    embed.py
    store.py
  query/
    guardrails.py
    retrieve.py
    generate.py
    llm/
      base.py
      groq.py
  app/
    ui.py
  prompts/
    system.md
data/                 # gitignore vectors/html if large; keep small samples
  raw/
  chunks/
  embeddings/
  chroma/
  retrieved/
  generated/
sources/
  urls.csv            # 15–25 URLs deliverable
samples/
  qa.md               # 5–10 Q&A deliverable
```

Ingestion is a CLI (or notebook cells 1–4). The app only runs the query path against an already-built Chroma store.

---

## 10. Data stores and trust boundary

| Store | Contents | Trust |
| --- | --- | --- |
| `data/raw` | Public HTML/text | Public only |
| `data/chunks` | Derived text + URLs | Public only |
| Chroma | Vectors + metadata | Local demo |
| `.env` | API keys | Secrets; never in artifacts |
| Query logs | Optional query_id + intent; **no PII** | Drop or redact |

The model never sees PAN, Aadhaar, account numbers, OTPs, emails, or phones. Guardrails redact or reject before retrieve/generate.

---

## 11. Failure modes

| Failure | Behavior |
| --- | --- |
| Fetch 4xx/5xx | Skip URL, record error in raw metadata; rest of corpus still indexes |
| Empty extract | Do not chunk; flag in load report |
| Chroma missing | UI error: run ingestion first |
| Retrieval scores all weak / no fact overlap | Refuse + official URL; **do not** call LLM to guess |
| Groq down | Surface error; retrieval artifact still saved (demo still shows RAG) |
| Out-of-corpus scheme | Refuse: this prototype covers HDFC AMC + four listed schemes |

---

## 12. What this architecture optimizes for

- **W1:** Explicit answer vs refuse gate.  
- **W2:** Short, cited, polite prompts.  
- **W3:** Tiny RAG with real URLs and visible retrieve step.

It does **not** optimize for production scale, auth, or live NAV/returns.
