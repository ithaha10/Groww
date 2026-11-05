const TRANSFORMERS_CDN = "https://cdn.jsdelivr.net/npm/@xenova/transformers@2.17.2";
const MODEL_ID = "Xenova/all-MiniLM-L6-v2";

const state = {
  extractor: null,
  loading: null,
  busy: false,
};

const $ = (id) => document.getElementById(id);

const form = $("ask-form");
const questionEl = $("question");
const askBtn = $("ask-btn");
const statusEl = $("status");
const statusText = $("status-text");
const resultEl = $("result");
const answerBadge = $("answer-badge");
const answerBody = $("answer-body");
const citationLink = $("citation-link");
const citationText = $("citation-text");
const updatedEl = $("updated");
const errorPanel = $("error-panel");
const errorText = $("error-text");

function setStatus(kind, text) {
  statusEl.dataset.state = kind;
  statusText.textContent = text;
}

async function loadModel() {
  if (state.extractor) return state.extractor;
  if (state.loading) return state.loading;

  state.loading = (async () => {
    setStatus("working", "Preparing assistant (first visit)…");
    const { pipeline, env } = await import(TRANSFORMERS_CDN);
    env.allowLocalModels = false;
    env.useBrowserCache = true;
    const extractor = await pipeline("feature-extraction", MODEL_ID, {
      quantized: true,
    });
    state.extractor = extractor;
    if (!state.busy) setStatus("ready", "Ready · facts-only");
    return extractor;
  })().catch((error) => {
    state.loading = null;
    setStatus("error", "Assistant failed to load");
    throw error;
  });

  return state.loading;
}

function cleanAnswerBody(text) {
  return String(text || "")
    .split("\n")
    .filter(
      (line) =>
        !/^\s*(source|citation)\s*:/i.test(line) &&
        !/^\s*last updated from sources\s*:/i.test(line)
    )
    .join("\n")
    .trim();
}

function shortUrl(url) {
  try {
    const parsed = new URL(url);
    const path = parsed.pathname === "/" ? "" : parsed.pathname;
    const label = `${parsed.hostname}${path}`;
    return label.length > 54 ? `${label.slice(0, 51)}…` : label;
  } catch {
    return url;
  }
}

function showError(message) {
  errorPanel.hidden = false;
  errorText.textContent = message;
}

function hideError() {
  errorPanel.hidden = true;
  errorText.textContent = "";
}

function render(data) {
  if (data.mode === "error") {
    resultEl.hidden = true;
    showError(data.error || "The server could not complete the request.");
    setStatus("error", "Request failed");
    return;
  }

  hideError();
  resultEl.hidden = false;
  answerBadge.dataset.mode = data.mode;
  answerBadge.textContent =
    data.mode === "refuse" ? "guardrail refusal" : "grounded answer";

  answerBody.textContent =
    cleanAnswerBody(data.answer_text) || "No answer text was returned.";

  if (data.citation_url) {
    citationLink.hidden = false;
    citationLink.href = data.citation_url;
    citationText.textContent = shortUrl(data.citation_url);
  } else {
    citationLink.hidden = true;
  }

  if (data.last_updated) {
    updatedEl.textContent = `fetched ${data.last_updated}`;
  } else {
    updatedEl.textContent = "";
  }

  setStatus(
    "ready",
    data.mode === "answer" ? "Answer grounded" : "Refused by guardrail"
  );
}

async function handleAsk(event) {
  event.preventDefault();
  if (state.busy) return;

  const question = questionEl.value.trim();
  if (!question) {
    questionEl.focus();
    return;
  }

  state.busy = true;
  askBtn.disabled = true;
  resultEl.hidden = true;
  hideError();

  try {
    const extractor = await loadModel();

    setStatus("working", "Understanding your question…");
    const output = await extractor(question, {
      pooling: "mean",
      normalize: true,
    });
    const embedding = Array.from(output.data);

    setStatus("working", "Searching official sources…");
    const response = await fetch("/api/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question, embedding }),
    });

    let data;
    try {
      data = await response.json();
    } catch {
      throw new Error(`Server returned HTTP ${response.status}.`);
    }

    if (!response.ok) {
      throw new Error(data.error || `Server returned HTTP ${response.status}.`);
    }

    render(data);
  } catch (error) {
    showError(error.message || String(error));
    setStatus("error", "Request failed");
  } finally {
    state.busy = false;
    askBtn.disabled = false;
  }
}

function wireExamples() {
  const examples = $("examples");
  if (!examples) return;
  examples.addEventListener("click", (event) => {
    const button = event.target.closest("button");
    if (!button) return;
    questionEl.value = button.textContent.trim();
    form.requestSubmit();
  });
}

form.addEventListener("submit", handleAsk);
wireExamples();
loadModel().catch(() => {
  /* status already reflects the failure */
});
