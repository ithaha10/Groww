"""Streamlit UI for the Groww Mutual Fund FAQ assistant."""

from __future__ import annotations

import html
import json
import re
import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.config import get_config  # noqa: E402
from src.query.pipeline import answer_question  # noqa: E402

DISCLAIMER = (
    "This assistant shares publicly available scheme facts only. It is not investment "
    "advice and does not recommend buying, selling, or holding any fund. Always verify "
    "details on the official scheme page or factsheet."
)

EXAMPLES = [
    "What is the expense ratio of HDFC Large Cap Fund Direct Growth?",
    "What is the lock-in for HDFC ELSS Tax Saver Fund Direct Plan Growth?",
    "How do I download a capital-gains statement?",
]

DATA = ROOT / "data"
URL_RE = re.compile(r"https?://\S+")

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Manrope:wght@400;500;600;700;800&family=Space+Grotesk:wght@500;600;700&display=swap');

:root {
  --groww: #00D09C;
  --groww-2: #00B4D8;
  --bg: #070B10;
  --panel: rgba(15, 22, 32, 0.72);
  --border: rgba(0, 208, 156, 0.18);
  --muted: #8BA3A0;
}

html, body, [class*="css"] {
  font-family: 'Manrope', system-ui, -apple-system, Segoe UI, sans-serif;
}

[data-testid="stAppViewContainer"] {
  background:
    radial-gradient(1100px 560px at 10% -12%, rgba(0, 208, 156, 0.18), transparent 60%),
    radial-gradient(900px 520px at 96% -6%, rgba(0, 180, 216, 0.15), transparent 55%),
    radial-gradient(1000px 700px at 50% 112%, rgba(0, 208, 156, 0.08), transparent 62%),
    #070B10;
  color: #E8F5F0;
}

[data-testid="stAppViewContainer"]::before {
  content: "";
  position: fixed;
  inset: 0;
  pointer-events: none;
  background-image:
    linear-gradient(rgba(255, 255, 255, 0.025) 1px, transparent 1px),
    linear-gradient(90deg, rgba(255, 255, 255, 0.025) 1px, transparent 1px);
  background-size: 46px 46px;
  -webkit-mask-image: radial-gradient(circle at 50% 18%, #000 0%, transparent 72%);
  mask-image: radial-gradient(circle at 50% 18%, #000 0%, transparent 72%);
  z-index: 0;
}

[data-testid="stHeader"] { background: transparent; }
.block-container { padding-top: 2rem; padding-bottom: 4rem; max-width: 1180px; }

.gw-hero {
  position: relative;
  display: flex;
  gap: 18px;
  align-items: center;
  flex-wrap: wrap;
  padding: 26px 28px;
  border-radius: 24px;
  border: 1px solid var(--border);
  background: linear-gradient(135deg, rgba(0, 208, 156, 0.10), rgba(0, 180, 216, 0.06) 45%, rgba(255, 255, 255, 0.02));
  box-shadow: 0 24px 70px rgba(0, 0, 0, 0.45), inset 0 1px 0 rgba(255, 255, 255, 0.06);
  overflow: hidden;
  margin-bottom: 18px;
}

.gw-hero::after {
  content: "";
  position: absolute;
  width: 300px;
  height: 300px;
  right: -90px;
  top: -140px;
  background: radial-gradient(circle, rgba(0, 208, 156, 0.35), transparent 70%);
  filter: blur(12px);
}

.gw-logo {
  width: 58px;
  height: 58px;
  border-radius: 17px;
  display: grid;
  place-items: center;
  font-family: 'Space Grotesk', sans-serif;
  font-weight: 700;
  font-size: 29px;
  color: #04120E;
  background: linear-gradient(135deg, #00D09C, #00B4D8);
  box-shadow: 0 10px 30px rgba(0, 208, 156, 0.35);
  flex: 0 0 auto;
}

.gw-title {
  font-family: 'Space Grotesk', sans-serif;
  font-size: 30px;
  font-weight: 700;
  letter-spacing: -0.5px;
  margin: 2px 0 0;
  background: linear-gradient(90deg, #E8F5F0, #9FF3DD);
  -webkit-background-clip: text;
  background-clip: text;
  color: transparent;
}

.gw-sub { color: #9BB7B2; margin: 5px 0 0; font-size: 14.5px; }

.gw-pill {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 8px 13px;
  border-radius: 999px;
  font-size: 12.5px;
  font-weight: 600;
  color: #B9F5E5;
  border: 1px solid rgba(0, 208, 156, 0.35);
  background: rgba(0, 208, 156, 0.10);
  margin-left: auto;
  white-space: nowrap;
}

.gw-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: #00D09C;
  box-shadow: 0 0 12px #00D09C;
}

.gw-stats { display: flex; gap: 12px; flex-wrap: wrap; margin: 6px 0 16px; }

.gw-stat {
  flex: 1 1 170px;
  padding: 14px 16px;
  border-radius: 16px;
  border: 1px solid rgba(255, 255, 255, 0.07);
  background: rgba(15, 22, 32, 0.55);
  backdrop-filter: blur(6px);
}

.gw-stat b {
  display: block;
  font-family: 'Space Grotesk', sans-serif;
  font-size: 17px;
  color: #E8F5F0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.gw-stat span {
  color: #8BA3A0;
  font-size: 11.5px;
  text-transform: uppercase;
  letter-spacing: 0.09em;
}

.gw-note {
  padding: 12px 16px;
  border-radius: 14px;
  border: 1px solid rgba(0, 208, 156, 0.25);
  background: rgba(0, 208, 156, 0.08);
  color: #CFF7EC;
  font-size: 13.5px;
}

.gw-disclaimer {
  color: #7E9994;
  font-size: 12.5px;
  line-height: 1.6;
  margin: 4px 0 6px;
}

.gw-section {
  font-family: 'Space Grotesk', sans-serif;
  font-size: 18px;
  font-weight: 600;
  margin: 14px 0 10px;
  color: #E8F5F0;
}

.gw-footer {
  margin-top: 34px;
  padding-top: 16px;
  border-top: 1px solid rgba(255, 255, 255, 0.07);
  color: #6E8783;
  font-size: 12px;
  text-align: center;
  letter-spacing: 0.02em;
}

.stButton > button, .stLinkButton > a {
  border-radius: 12px !important;
  border: 1px solid rgba(0, 208, 156, 0.35) !important;
  background: linear-gradient(135deg, rgba(0, 208, 156, 0.16), rgba(0, 180, 216, 0.10)) !important;
  color: #DFFFF7 !important;
  font-weight: 600 !important;
  transition: transform 0.16s ease, box-shadow 0.16s ease, border-color 0.16s ease !important;
}

.stButton > button:hover, .stLinkButton > a:hover {
  transform: translateY(-1px);
  border-color: #00D09C !important;
  box-shadow: 0 10px 26px rgba(0, 208, 156, 0.22) !important;
}

.stButton > button[kind="primary"] {
  background: linear-gradient(135deg, #00D09C, #00B4D8) !important;
  color: #04120E !important;
  border: none !important;
  box-shadow: 0 12px 30px rgba(0, 208, 156, 0.28) !important;
}

.stTextArea textarea, .stTextInput input, [data-baseweb="select"] > div {
  background: rgba(9, 14, 20, 0.85) !important;
  color: #E8F5F0 !important;
  border: 1px solid rgba(255, 255, 255, 0.10) !important;
  border-radius: 14px !important;
}

.stTextArea textarea:focus, .stTextInput input:focus {
  border-color: #00D09C !important;
  box-shadow: 0 0 0 1px rgba(0, 208, 156, 0.35), 0 0 24px rgba(0, 208, 156, 0.12) !important;
}

[data-testid="stVerticalBlockBorderWrapper"] {
  border-radius: 20px !important;
  border: 1px solid rgba(255, 255, 255, 0.08) !important;
  background: linear-gradient(160deg, rgba(15, 22, 32, 0.88), rgba(10, 15, 21, 0.78)) !important;
  box-shadow: 0 18px 48px rgba(0, 0, 0, 0.35) !important;
  padding: 4px 6px;
}

.stTabs [data-baseweb="tab-list"] {
  gap: 6px;
  background: rgba(9, 14, 20, 0.6);
  padding: 6px;
  border-radius: 14px;
  border: 1px solid rgba(255, 255, 255, 0.06);
}

.stTabs [data-baseweb="tab"] { border-radius: 10px; color: #8BA3A0; font-weight: 600; }
.stTabs [aria-selected="true"] { background: rgba(0, 208, 156, 0.14) !important; color: #DFFFF7 !important; }
.stTabs [data-baseweb="tab-highlight"] { background: transparent !important; }
.stTabs [data-baseweb="tab-border"] { display: none; }

[data-testid="stAlert"] {
  border-radius: 16px !important;
  border: 1px solid rgba(0, 208, 156, 0.25) !important;
  background: rgba(0, 208, 156, 0.07) !important;
  color: #D8FBF1 !important;
}

[data-testid="stDataFrame"] {
  border-radius: 16px;
  overflow: hidden;
  border: 1px solid rgba(255, 255, 255, 0.07);
}

[data-testid="stCaptionContainer"] p { color: #7E9994 !important; }
hr { border-color: rgba(255, 255, 255, 0.08) !important; }
#MainMenu, footer { visibility: hidden; }

@media (max-width: 720px) {
  .gw-pill { margin-left: 0; }
  .gw-title { font-size: 25px; }
}
</style>
"""


def _read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"error": f"Could not read {path.name}: {exc}"}


def _read_jsonl(path: Path) -> list[dict]:
    rows: list[dict] = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rows.append(json.loads(line))
    except Exception:
        return rows
    return rows


def _latest(directory: Path) -> Path | None:
    if not directory.exists():
        return None
    files = [p for p in directory.glob("*.json") if p.is_file()]
    return max(files, key=lambda p: p.stat().st_mtime) if files else None


def _collection_count(config: dict) -> int | None:
    try:
        import chromadb

        chroma_cfg = config.get("chroma") or {}
        persist_dir = ROOT / str(chroma_cfg.get("persist_dir", "data/chroma"))
        name = str(chroma_cfg.get("collection", "groww_mf_faq"))
        if not persist_dir.exists():
            return None
        client = chromadb.PersistentClient(path=str(persist_dir))
        return client.get_collection(name).count()
    except Exception:
        return None


def _answer_card(payload: dict) -> None:
    mode = payload.get("mode")
    if mode == "error":
        st.error(payload.get("error") or "Generation failed. The retrieval artifact is saved.")
        return

    if mode == "refuse":
        message = URL_RE.sub("", payload.get("answer_text") or "").strip()
        st.warning(message or "I can't help with that.")
        url = payload.get("citation_url")
        if url:
            st.link_button("Open official source", url)
        return

    answer = payload.get("answer_text") or ""
    body = answer.split("\n\nSource:")[0].strip()
    with st.container(border=True):
        st.markdown('<div class="gw-section">Answer</div>', unsafe_allow_html=True)
        st.markdown(body)
        url = payload.get("citation_url")
        if url:
            st.link_button("Open official source", url)
        last_updated = payload.get("last_updated")
        if last_updated:
            st.caption(f"Last updated from sources: {last_updated}")


st.set_page_config(
    page_title="Groww Mutual Fund FAQ",
    page_icon=None,
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown(CSS, unsafe_allow_html=True)

config = get_config()
count = _collection_count(config)
scheme_count = len(
    {
        s.get("entity_id")
        for s in (config.get("sources") or [])
        if s.get("entity_type") == "scheme" and s.get("entity_id")
    }
)
model = (config.get("llm") or {}).get("model") or "not configured"

st.markdown(
    """
    <div class="gw-hero">
      <div class="gw-logo">G</div>
      <div>
        <h1 class="gw-title">Groww Mutual Fund FAQ</h1>
        <p class="gw-sub">Ask factual questions about HDFC schemes. Every answer cites one official page.</p>
      </div>
      <div class="gw-pill"><span class="gw-dot"></span> Facts-only. No investment advice.</div>
    </div>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    f"""
    <div class="gw-stats">
      <div class="gw-stat"><b>{count or 0}</b><span>Indexed chunks</span></div>
      <div class="gw-stat"><b>{scheme_count}</b><span>HDFC schemes</span></div>
      <div class="gw-stat"><b>{html.escape(str(model))}</b><span>LLM model</span></div>
    </div>
    <div class="gw-disclaimer">{html.escape(DISCLAIMER)}</div>
    """,
    unsafe_allow_html=True,
)

if not count:
    st.warning(
        "The Chroma collection is empty. Build it first:\n\n"
        "```\npython -m src.ingest.run --phase all\n```"
    )

if "question" not in st.session_state:
    st.session_state.question = ""
if "last_result" not in st.session_state:
    st.session_state.last_result = None

st.markdown('<div class="gw-section">Try an example</div>', unsafe_allow_html=True)
cols = st.columns(3)
for col, example in zip(cols, EXAMPLES):
    if col.button(example, width="stretch"):
        st.session_state.question = example
        st.session_state.last_result = None
        st.rerun()

st.markdown('<div class="gw-section">Ask a fact</div>', unsafe_allow_html=True)
question = st.text_area(
    "Question",
    key="question",
    height=105,
    placeholder="e.g. What is the exit load of HDFC Mid Cap Fund Direct Growth?",
    label_visibility="collapsed",
)
submitted = st.button("Ask", type="primary")

if submitted:
    if not question.strip():
        st.warning("Please enter a question.")
    else:
        with st.spinner("Retrieving official chunks..."):
            try:
                st.session_state.last_result = answer_question(question, config)
            except Exception as exc:
                st.session_state.last_result = {
                    "mode": "error",
                    "error": f"Query failed: {exc}",
                }

result = st.session_state.last_result
if result:
    _answer_card(result)
    if result.get("query_id"):
        st.caption(f"Query id: {result['query_id']}")

st.divider()
st.markdown('<div class="gw-section">Demo artifacts</div>', unsafe_allow_html=True)
tabs = st.tabs(
    [
        "Scrape",
        "Loaded docs",
        "Chunks",
        "Embeddings",
        "Chroma",
        "Latest retrieved",
        "Latest generated",
    ]
)

with tabs[0]:
    report_path = DATA / "raw" / "scrape_report.json"
    if report_path.exists():
        report = _read_json(report_path)
        st.write(
            f"ok: {report.get('ok_count')} | failed: {report.get('failed_count')} | "
            f"fetched: {report.get('fetched_at')}"
        )
        st.json(report)
    else:
        st.write("No scrape report yet.")
    html_dir = DATA / "raw" / "html"
    html_files = sorted(p.name for p in html_dir.glob("*.html")) if html_dir.exists() else []
    st.write(f"Raw HTML files: {len(html_files)}")
    if html_files:
        st.code("\n".join(html_files))

with tabs[1]:
    docs = _read_jsonl(DATA / "raw" / "documents.jsonl")
    if docs:
        st.dataframe(
            [
                {
                    "doc_id": d.get("doc_id"),
                    "title": d.get("title"),
                    "entity_id": d.get("entity_id"),
                    "chars": len(d.get("text") or ""),
                    "url": d.get("url"),
                }
                for d in docs
            ],
            width="stretch",
        )
        with st.expander("View a document"):
            choice = st.selectbox("Document", [d.get("doc_id") for d in docs])
            selected = next((d for d in docs if d.get("doc_id") == choice), None)
            if selected:
                st.write(selected.get("text"))
    else:
        st.write("No loaded documents. Run the load phase.")

with tabs[2]:
    chunks = _read_jsonl(DATA / "chunks" / "chunks.jsonl")
    if chunks:
        st.write(f"Total chunks: {len(chunks)}")
        st.dataframe(
            [
                {
                    "chunk_id": c.get("chunk_id"),
                    "doc_id": c.get("doc_id"),
                    "section": c.get("section"),
                    "is_fact": c.get("is_fact"),
                    "chars": len(c.get("text") or ""),
                    "source_url": c.get("source_url"),
                }
                for c in chunks
            ],
            width="stretch",
        )
        with st.expander("View a chunk"):
            choice = st.selectbox("Chunk", [c.get("chunk_id") for c in chunks])
            selected = next((c for c in chunks if c.get("chunk_id") == choice), None)
            if selected:
                st.json(selected)
    else:
        st.write("No chunks. Run the chunk phase.")

with tabs[3]:
    meta = _read_jsonl(DATA / "embeddings" / "meta.jsonl")
    vectors = DATA / "embeddings" / "vectors.npy"
    if meta:
        st.write(
            f"Vectors: {len(meta)} | dim: {meta[0].get('dim')} | "
            f"model: {(config.get('embedding') or {}).get('model')}"
        )
        st.dataframe(
            [
                {
                    "chunk_id": m.get("chunk_id"),
                    "section": m.get("section"),
                    "dim": m.get("dim"),
                    "source_url": m.get("source_url"),
                }
                for m in meta
            ],
            width="stretch",
        )
    else:
        st.write("No embeddings metadata. Run the embed phase.")
    if vectors.exists():
        st.caption(f"Vector matrix: {vectors.name} ({vectors.stat().st_size} bytes)")

with tabs[4]:
    info_path = DATA / "chroma" / "collection_info.json"
    if info_path.exists():
        st.json(_read_json(info_path))
    else:
        st.write("No collection info. Run the store phase.")

with tabs[5]:
    latest = _latest(DATA / "retrieved")
    if latest:
        st.caption(latest.name)
        st.json(_read_json(latest))
    else:
        st.write("No retrieval artifacts yet.")

with tabs[6]:
    latest = _latest(DATA / "generated")
    if latest:
        st.caption(latest.name)
        st.json(_read_json(latest))
    else:
        st.write("No generated artifacts yet.")

st.markdown(
    '<div class="gw-footer">Groww MF FAQ prototype · small-corpus RAG · '
    "official public pages only</div>",
    unsafe_allow_html=True,
)
