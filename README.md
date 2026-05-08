# Adaptive RAG System

A production-grade local retrieval-augmented generation application using FastAPI, LangChain, FAISS, and Ollama.

## Features

- Multi-file ingestion from `data/raw/`
- Local Ollama embeddings with `nomic-embed-text`
- Persistent FAISS vector database in `vector_db/`
- Retrieval, local LLM reranking, grounded answer generation, and hallucination checks
- Local LLM-as-judge evaluation logged to `data/processed/evaluations.jsonl`
- JSONL feedback capture
- Offline improvement suggestions based on low-quality evaluation records
- Request latency, retrieval counts, failures, and evaluation score logging

## Setup

1. Install Ollama from `https://ollama.com`.
2. Start Ollama and pull the required local models:

```bash
ollama pull llama3
ollama pull nomic-embed-text
```

3. Create and activate a Python environment.
4. Install dependencies:

```bash
pip install -r requirements.txt
```

5. Configure `.env`:

```env
OLLAMA_BASE_URL=http://127.0.0.1:11434
GENERATION_MODEL=llama3
EMBEDDING_MODEL=nomic-embed-text
```

6. Add documents to `data/raw/` as `.txt` or `.md` files.

## Run

Start the backend:

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Build or run the dashboard:

```bash
npm run dev
```

## API Endpoints

- `GET /status` - health check with Ollama diagnostics
- `POST /ingest` - ingest documents into FAISS with local embeddings
- `POST /query` - run retrieve, rerank, generate, grounding check, evaluate, and log
- `POST /evaluate` - evaluate a supplied query/context/answer
- `POST /feedback` - submit user feedback
- `POST /improve` - analyze evaluation logs and suggest tuning changes
- `POST /debug/retrieval` - inspect initial and reranked retrieval results

## Notes

- The system is fully local. No API key is required.
- If Ollama is offline, LLM-dependent endpoints return warning JSON instead of crashing.
- Re-run `/ingest` after switching embedding models because FAISS vectors are model-specific.
