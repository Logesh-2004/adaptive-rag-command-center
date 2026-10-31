# Adaptive RAG System

A retrieval-augmented generation app with a FastAPI backend and a Next.js dashboard. Groq generates answers; local BM25 search retrieves document chunks without a separate embedding or reranking model.

## Features

- Ingest `.txt`, `.md`, and `.pdf` files from `data/raw/`
- Report and skip unreadable PDF files while continuing ingestion
- Persist a local BM25 text index under `vector_db/bm25_store/`
- Generate and stream grounded answers with Groq
- Rank retrieved passages with BM25, query-phrase matches, file-name matches, and passage quality
- Expand queries from an editable synonym file plus pseudo-relevance feedback
- Check grounding with deterministic token-overlap heuristics
- Capture JSONL evaluation, feedback, and system activity records
- Suggest improvements from prior evaluation records and negative user feedback
- Rebuild the index, review tuning, re-trace retrieval and rate answers from the dashboard
- Watch each question fly through a 3D wormhole: one universe per pipeline step, then land with its scores

## Setup

1. Install Python 3.10+ and Node.js.
2. Create and activate a Python environment, then install the backend dependencies:

```bash
pip install -r requirements.txt
```

3. Copy `.env.example` to `.env` and set a Groq API key. The key stays on the backend and must never be placed in browser code or a `NEXT_PUBLIC_` variable.

```env
GROQ_API_KEY=your-groq-api-key
GROQ_MODEL=openai/gpt-oss-20b
```

4. Add documents to `data/raw/` as `.txt`, `.md`, or `.pdf` files.
5. Install the dashboard dependencies:

```bash
npm install
```

6. Start the backend and dashboard in separate terminals:

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
npm run dev
```

7. Build the BM25 index before querying, with the dashboard's **Rebuild index** button or `POST /ingest`.

## Tests

```bash
pip install -r requirements-dev.txt
python -m pytest
```

The tests use a small temporary corpus and a fake Groq client, so they make no network calls.

## Retrieval design

Answer generation uses Groq's chat completions API. To keep Groq as the only hosted model provider, this project searches document text locally with BM25 and checks grounding with token overlap. Query expansions, source hints, and lexical scoring help rank passages before Groq generates an answer. No other model service is called for retrieval or evaluation.

Retrieval is topic-neutral: query rewrites come from `data/query_expansions.json` (phrase -> extra terms, edit it for your corpus) and from distinctive terms shared by the top results. Passages get extra weight when they contain adjacent word pairs from the question or when their file name shares words with it.

BM25 relies on matching words and terms. Questions that use different wording from the indexed documents may retrieve less relevant passages than semantic embedding search. Re-ingest documents after switching from the previous FAISS index; the existing FAISS files are no longer used.

## API endpoints

- `GET /status` - Groq configuration and local index health
- `POST /ingest` - create the BM25 index from `data/raw/`
- `POST /query` - retrieve, rank, generate, evaluate, and log an answer
- `POST /query/stream` - stream a generated answer
- `POST /evaluate` - evaluate a supplied query, context, and answer locally
- `POST /feedback` - submit user feedback
- `POST /improve` - analyze evaluation records and suggest tuning changes
- `POST /debug/retrieval` - inspect retrieved and ranked passages

## Dashboard

The home page (`/`) is a 3D relay built with Three.js through React Three Fiber:

- The ship launches from its pad when you send a question, then crosses five gates, one per pipeline step: I The Archive (retrieve), II The Sorting Drift (rank), III The Narrows (compress), IV The Forge (generate), V The Proving Ground (ground).
- The ship's progress follows the backend's real streaming events. Each universe is shown for at least 1.4 seconds so its title card can be read.
- If the backend runs a corrective retry, the ship flies a loop before exiting.
- After landing, the scores appear as call-outs around the ship on wide screens, and inside the answer panel on phones and tablets.
- The header has **Rebuild index** and **Review tuning**; the evidence card has **Run trace**.
- With reduced motion turned on, the flight is near-instant and the crossing effects are skipped.
- `/classic` keeps the earlier flat dashboard. Browsers without WebGL are pointed to it.

## Logging

Query, evaluation, and feedback records are appended to `data/processed/*.jsonl` (not committed to git). Each file rotates to `<name>.1.jsonl` at `LOG_MAX_BYTES` (5 MB by default). Full prompts and retrieved passages are logged only when `RAG_DEBUG_LOGS=true`.

## Deployment notes

Set `GROQ_API_KEY` as a server-side environment variable on the backend host. The dashboard can be deployed separately; set `RAG_BACKEND_URL` on the dashboard server to the backend URL (read only by the server-side proxy). The local BM25 index is stored on disk, so a deployment with ephemeral storage should persist that directory or run ingestion again after each fresh deploy.
