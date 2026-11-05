# Groww Mutual Fund FAQ Assistant

A small, facts-only FAQ assistant for mutual fund schemes. Ask a factual question (expense ratio, exit load, minimum SIP, ELSS lock-in, riskometer, benchmark, how to download a statement) and get a short answer with one source link. It does not give investment advice.

- **Live prototype:** [https://growwmffaq.streamlit.app/]
- **Code:** https://github.com/ithaha10/Groww
- **Product chosen:** Groww
- **AMC in scope:** HDFC Mutual Fund

> **Facts-only. No investment advice.**

---

## What it does

- Answers factual questions about 4 HDFC schemes and common investor tasks (statements, tax documents).
- Retrieves the most relevant passages from a small indexed corpus and generates a short answer grounded in them (RAG).
- Shows a source link with every answer and a "Last updated from sources" note.
- Declines opinion and portfolio questions such as "Should I buy this fund?" and points to educational material instead.
- Has a simple UI: welcome line, 3 example questions and a disclaimer.

## Scope

| Item | Detail |
|---|---|
| AMC | HDFC Mutual Fund |
| Schemes | HDFC Large Cap Fund, HDFC Flexi Cap Fund (listed on Groww as HDFC Equity Fund), HDFC ELSS Tax Saver Fund, HDFC Mid Cap Fund |
| Question types | Expense ratio, exit load, minimum SIP, lock-in (ELSS), riskometer, benchmark, how to download capital-gains statement, tax proof for Section 80C |
| Out of scope | Advice, recommendations, return calculations or comparisons, personal portfolio questions |

## How it works

```
scrape -> load -> chunk -> embed -> store (Chroma) -> retrieve -> LLM answer -> Streamlit UI
```

| Step | What happens | Code |
|---|---|---|
| Scrape | Downloads public pages listed in `config.yaml` and writes a scrape report | `src/ingest/scrape.py` |
| Load | Extracts clean text from the saved HTML | `src/ingest/load.py` |
| Chunk | Splits documents into 333 chunks | `src/ingest/chunk.py` |
| Embed | Creates 384-dimension vectors with `sentence-transformers/all-MiniLM-L6-v2` | `src/ingest/embed.py` |
| Store | Saves vectors in a ChromaDB collection (`groww_mf_faq`) at `data/chroma` | `src/ingest/store.py` |
| Answer | Retrieves top chunks, prompts an LLM via Groq, returns a short answer with a citation | `src/query/`, `src/prompts/` |
| UI | Streamlit app | `src/app/ui.py` |

## Setup

**Requirements:** Python 3 (developed on 3.14) and a free [Groq](https://console.groq.com) API key.

```bash
git clone https://github.com/ithaha10/Groww.git
cd Groww
pip install -r requirements.txt
```

Create your environment file:

```bash
cp .env.example .env
```

Then edit `.env`:

```
GROQ_API_KEY=your-groq-key
GROQ_MODEL=your-groq-model-id
```

Pick a current chat model ID from Groq's model list. The other keys in `.env.example` are not needed for the default Groq setup. Never commit `.env`.

**Build the index** (the repo already includes a prebuilt index in `data/chroma`, so you can skip this unless you change the sources):

```bash
python -m src.ingest.run --phase all
```

**Run the app:**

```bash
streamlit run src/app/ui.py
```

## Deployment

The app is hosted on Streamlit Community Cloud from this repo.

- Main file: `src/app/ui.py`
- Secrets are set in the app's **Settings -> Secrets** (TOML format, values in quotes):

```toml
GROQ_API_KEY = "your-groq-key"
GROQ_MODEL = "your-groq-model-id"
```

- The prebuilt Chroma index is committed in `data/chroma`, so the deployed app does not rebuild it on startup.

## Source list

17 public URLs were configured; 10 were fetched and indexed (fetched 5 Nov 2026). All sources are public pages.

### Indexed (10)

| # | Publisher | URL |
|---|---|---|
| 1 | Groww | https://groww.in/mutual-funds/amc/hdfc-mutual-funds |
| 2 | Groww | https://groww.in/mutual-funds/hdfc-large-cap-fund-direct-growth |
| 3 | Groww | https://groww.in/mutual-funds/hdfc-equity-fund-direct-growth |
| 4 | Groww | https://groww.in/mutual-funds/hdfc-elss-tax-saver-fund-direct-plan-growth |
| 5 | Groww | https://groww.in/mutual-funds/hdfc-mid-cap-fund-direct-growth |
| 6 | Groww Help | https://groww.in/help/mutual-funds/mf-others/how-to-download-capital-gain-report--50 |
| 7 | Groww Help | https://groww.in/help/my-account/ma-others/where-can-i-get-the-tax-proof-for-section-80c |
| 8 | AMFI | https://www.amfiindia.com/investor |
| 9 | SEBI | https://investor.sebi.gov.in/ |
| 10 | SEBI | https://investor.sebi.gov.in/iematerial.html |

### Configured but not indexed (7)

| URL | Result |
|---|---|
| https://groww.in/p/elss | 404, page not found |
| https://groww.in/p/sip | 404, page not found |
| https://www.hdfcfund.com/mutual-funds/factsheets | 403, blocked automated requests |
| https://www.hdfcfund.com/explore/mutual-funds/hdfc-large-cap-fund/direct | 403, blocked |
| https://www.hdfcfund.com/explore/mutual-funds/hdfc-flexi-cap-fund/direct | 403, blocked |
| https://www.hdfcfund.com/explore/mutual-funds/hdfc-elss-tax-saver-fund/direct | 403, blocked |
| https://www.hdfcfund.com/explore/mutual-funds/hdfc-mid-cap-fund/direct | 403, blocked |

The full scrape report is in `data/raw/scrape_report.json`.

## Sample Q&A

> Run each question in the app and paste the actual answer and link below.

| # | Question | Assistant's answer | Source link |
|---|---|---|---|
| 1 | What is the expense ratio of HDFC Large Cap Fund? | The expense ratio for HDFC Large Cap Fund is 1.02%. | https://groww.in/mutual-funds/hdfc-large-cap-fund-direct-growth |
| 2 | What is the lock-in period for HDFC ELSS Tax Saver Fund? | The lock-in period for the HDFC ELSS Tax Saver Fund is 3 years. | https://groww.in/mutual-funds/hdfc-elss-tax-saver-fund-direct-plan-growth |
| 3 | What is the exit load of HDFC Mid Cap Fund? | The exit load for the HDFC Mid Cap Fund is 1% if redeemed within 1 year. | https://groww.in/mutual-funds/hdfc-mid-cap-fund-direct-growth |
| 4 | What is the minimum SIP amount for HDFC Flexi Cap Fund? | The minimum SIP amount for HDFC Equity Fund Direct Growth is ₹100. | https://groww.in/mutual-funds/hdfc-equity-fund-direct-growth |
| 5 | What is the benchmark and riskometer rating of HDFC Large Cap Fund? | The HDFC Large Cap Fund Direct Growth is rated Very High risk. The provided sources do not state the fund's benchmark. | https://groww.in/mutual-funds/hdfc-large-cap-fund-direct-growth |
| 6 | How do I download a capital-gains statement? | To download a capital-gains statement, go to your profile, select 'Reports', and under 'Tax' choose 'Mutual Fund - Capital Gains'. Select the desired financial year and click 'Download'. | https://groww.in/help/mutual-funds/mf-others/how-to-download-capital-gain-report--50 |
| 7 | Where can I get tax proof for Section 80C? | You can obtain your Section 80C tax proof by downloading the Mutual Fund-ELSS statement. | https://groww.in/help/mutual-funds/mf-others/
| 8 | Should I buy HDFC Mid Cap Fund? (advice, should be refused) | I can only share publicly available scheme facts, not investment advice. For investor education, see | https://investor.sebi.gov.in/ |

## Disclaimer

Text shown in the app:

> This assistant shares publicly available scheme facts only. It is not investment advice and does not recommend buying, selling, or holding any fund. Always verify details on the official scheme page or factsheet.

## Known limits

- **Small corpus.** Only 10 pages are indexed, so some questions will return "not found".
- **AMC pages are missing.** hdfcfund.com returned HTTP 403 to the scraper, so the HDFC factsheet and scheme pages are not indexed yet. Scheme-level facts currently come from Groww's scheme pages, not from the AMC or SEBI. Always verify on the official AMC page.
- **Facts can go stale.** Expense ratios, exit loads and similar figures change. The app shows when sources were last fetched; the index must be rebuilt to refresh them.
- **No performance data.** The assistant does not compute or compare returns.
- **LLM output can still be wrong.** Answers are grounded in retrieved text but are not guaranteed correct.
- **Do not enter personal data** such as PAN, Aadhaar, account numbers, OTPs, emails or phone numbers. The app does not need them and does not ask for them.

## Roadmap

- Index the blocked HDFC AMC pages (saved manually or via an allowed source) and add the SEBI/AMFI scheme documents.
- Add a small evaluation set to measure answer accuracy and citation correctness.
- Automate periodic refresh of the index.

## Project structure

```
Groww/
├── config.yaml          # sources and settings
├── requirements.txt
├── .env.example         # environment variable template
├── data/
│   ├── raw/             # scraped pages and reports
│   ├── chunks/          # chunked text
│   ├── embeddings/      # embedding metadata
│   └── chroma/          # vector index
└── src/
    ├── ingest/          # scrape, load, chunk, embed, store
    ├── query/           # retrieval and answer generation
    ├── prompts/         # LLM prompts
    └── app/ui.py        # Streamlit UI
```
