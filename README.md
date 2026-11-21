# DocMind AI — private, offline document Q&A

Upload PDFs, Word files or text, then chat with them. Everything runs locally: the LLM (Ollama),
embeddings, vector search (Chroma) and database (SQLite). No API keys, no internet needed after setup.

**Features:** login/register (JWT) · per-user isolated indexes · live processing status ·
token-by-token streaming · page-level citations · model switcher · per-answer latency and tokens/sec ·
auto-summary per document · Docker Compose one-command run.

## Architecture

```
React (Vite) ──/api──▶ FastAPI ──▶ Ollama (LLM + embeddings)
                          ├──▶ ChromaDB (vectors, one collection per user)
                          └──▶ SQLite (users, documents, status)
Upload → background task: parse → chunk → embed → store → summarize
Chat   → embed question → top-k search → prompt with context → stream tokens (SSE)
```

## Option A — Run locally (best for development)

1. Install [Ollama](https://ollama.com), Python 3.11+, Node 18+.
2. Pull models:
   ```bash
   ollama pull llama3.2:3b
   ollama pull nomic-embed-text
   ```
3. Backend:
   ```bash
   cd backend
   python -m venv venv
   source venv/bin/activate        # Windows: venv\Scripts\activate
   pip install -r requirements.txt
   uvicorn app.main:app --reload
   ```
   API docs: http://localhost:8000/docs
4. Frontend (new terminal):
   ```bash
   cd frontend
   npm install
   npm run dev
   ```
   Open http://localhost:5173, register, upload a document, ask questions.

## Option B — Docker Compose

```bash
docker compose up --build -d
docker compose exec ollama ollama pull llama3.2:3b
docker compose exec ollama ollama pull nomic-embed-text
```
Open http://localhost:3000. Set `SECRET_KEY` in your environment for real use.

## Choosing a model

| RAM | Suggested `LLM_MODEL` |
|---|---|
| 8 GB, no GPU | `llama3.2:3b` or `qwen2.5:3b` |
| 16 GB | `qwen2.5:7b` or `llama3.1:8b` |
| GPU 6 GB+ | any 7-8B model |

Pull extra models with `ollama pull <name>`; they appear in the UI dropdown so you can compare speed and quality.

## Configuration (env vars)

`OLLAMA_HOST`, `LLM_MODEL`, `EMBED_MODEL`, `SECRET_KEY`, `DATA_DIR`.
Chunk size and top-k are in `backend/app/config.py`.

## Troubleshooting

- **"Connection refused" on chat/upload:** Ollama isn't running (`ollama serve`) or the models aren't pulled.
- **Status "failed — No extractable text":** the PDF is scanned. Add OCR (`pytesseract`) in `rag.parse_file`.
- **Slow answers:** use a smaller model; first request also loads the model into memory.

## Roadmap (ideas to extend for your resume)

1. Reranking with a cross-encoder (`sentence-transformers`) after retrieving top-10.
2. Evaluation script: 20-30 Q&A pairs, measure retrieval hit-rate@4 and report it here.
3. Watched "inbox" folder that auto-ingests new files (`watchdog`).
4. Chat history per user and conversation memory.
5. OCR for scanned PDFs; Whisper for audio files.
6. Tests + GitHub Actions CI.
