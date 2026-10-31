# Adaptive RAG System

A retrieval-augmented generation app with a FastAPI backend and a Next.js dashboard. Groq generates answers; local BM25 search retrieves document chunks without a separate embedding or reranking model.

## Features

- Ingest `.txt`, `.md`, and `.pdf` files from `data/raw/`
- Report and skip unreadable PDF files while continuing ingestion
- Persist a local BM25 text index under `vector_db/bm25_store/`
- Generate and stream grounded answers with Groq
- Rank retrieved passages with lexical overlap, intent, and source metadata
- Check grounding with deterministic token-overlap heuristics
- Capture JSONL evaluation, feedback, and system activity records
- Suggest improvements from prior evaluation records

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

7. Call `POST /ingest` to build the BM25 index before querying.

## Retrieval design

Answer generation uses Groq's chat completions API. To keep Groq as the only hosted model provider, this project searches document text locally with BM25 and checks grounding with token overlap. Query expansions, source hints, and lexical scoring help rank passages before Groq generates an answer. No other model service is called for retrieval or evaluation.

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

## Deployment notes

Set `GROQ_API_KEY` as a server-side environment variable on the backend host. The dashboard can be deployed separately; configure its API proxy to point to the backend URL. The local BM25 index is stored on disk, so a deployment with ephemeral storage should persist that directory or run ingestion again after each fresh deploy.
