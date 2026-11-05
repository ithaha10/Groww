"""Streamlit UI for the Groww Mutual Fund FAQ assistant."""

from __future__ import annotations

import html
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


def _answer_card(payload: dict) -> None:
    mode = payload.get("mode")
    if mode == "error":
        st.error(payload.get("error") or "The answer could not be generated. Please try again.")
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
scheme_count = len(
    {
        s.get("entity_id")
        for s in (config.get("sources") or [])
        if s.get("entity_type") == "scheme" and s.get("entity_id")
    }
)
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
      <div class="gw-stat"><b>{scheme_count}</b><span>HDFC schemes</span></div>
    </div>
    <div class="gw-disclaimer">{html.escape(DISCLAIMER)}</div>
    """,
    unsafe_allow_html=True,
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
        with st.spinner("Searching official sources..."):
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

st.markdown(
    '<div class="gw-footer">Groww MF FAQ prototype · small-corpus RAG · '
    "official public pages only</div>",
    unsafe_allow_html=True,
)
