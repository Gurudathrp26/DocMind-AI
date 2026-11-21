"""Document parsing, embedding, retrieval and streaming answers (all local)."""
import json
import time
import uuid
from pathlib import Path

import chromadb
import ollama

from .config import (
    CHROMA_DIR, CHUNK_OVERLAP, CHUNK_SIZE, EMBED_MODEL, LLM_MODEL, OLLAMA_HOST, TOP_K,
)
from .db import Document, SessionLocal

llm = ollama.Client(host=OLLAMA_HOST)
chroma = chromadb.PersistentClient(path=str(CHROMA_DIR))

SYSTEM_PROMPT = (
    "You are a helpful assistant that answers ONLY from the provided context. "
    "Cite the source after each claim like [filename p3]. "
    "If the answer is not in the context, say you don't know."
)


def collection(user_id: int):
    return chroma.get_or_create_collection(f"user_{user_id}", metadata={"hnsw:space": "cosine"})


# ---------- parsing ----------
def parse_file(path: str) -> list[tuple[int, str]]:
    """Return a list of (page_number, text)."""
    ext = Path(path).suffix.lower()
    if ext == ".pdf":
        from pypdf import PdfReader

        return [(i, p.extract_text() or "") for i, p in enumerate(PdfReader(path).pages, 1)]
    if ext == ".docx":
        import docx

        text = "\n".join(p.text for p in docx.Document(path).paragraphs)
        return [(1, text)]
    return [(1, Path(path).read_text(errors="ignore"))]


def chunk_text(text: str, size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    text = " ".join(text.split())
    out, i = [], 0
    while i < len(text):
        piece = text[i : i + size].strip()
        if piece:
            out.append(piece)
        i += size - overlap
    return out


# ---------- ingestion (runs in a background task) ----------
def _set(db, doc, **fields):
    for k, v in fields.items():
        setattr(doc, k, v)
    db.commit()


def ingest_document(doc_id: int) -> None:
    db = SessionLocal()
    doc = db.get(Document, doc_id)
    try:
        _set(db, doc, status="parsing")
        pages = parse_file(doc.path)
        ids, texts, metas = [], [], []
        for page_no, text in pages:
            for c in chunk_text(text):
                ids.append(str(uuid.uuid4()))
                texts.append(c)
                metas.append({"doc_id": doc.id, "page": page_no, "filename": doc.filename})
        if not texts:
            raise ValueError("No extractable text (scanned PDF? add OCR).")

        _set(db, doc, status="embedding")
        col = collection(doc.user_id)
        batch = 32
        for i in range(0, len(texts), batch):
            embs = llm.embed(model=EMBED_MODEL, input=texts[i : i + batch])["embeddings"]
            col.add(
                ids=ids[i : i + batch],
                documents=texts[i : i + batch],
                embeddings=embs,
                metadatas=metas[i : i + batch],
            )
        _set(db, doc, status="ready", chunks=len(texts))

        # Optional auto-summary (does not block "ready")
        try:
            sample = " ".join(texts[:4])[:3000]
            r = llm.chat(
                model=LLM_MODEL,
                messages=[{"role": "user",
                           "content": f"Summarize this document in 3 short bullet points:\n\n{sample}"}],
            )
            _set(db, doc, summary=r["message"]["content"])
        except Exception:
            pass
    except Exception as e:  # noqa: BLE001
        _set(db, doc, status="failed", error=str(e)[:500])
    finally:
        db.close()


def delete_document_vectors(user_id: int, doc_id: int) -> None:
    try:
        collection(user_id).delete(where={"doc_id": doc_id})
    except Exception:
        pass


# ---------- retrieval + streaming answer ----------
def retrieve(user_id: int, question: str, k: int = TOP_K) -> list[dict]:
    col = collection(user_id)
    if col.count() == 0:
        return []
    qe = llm.embed(model=EMBED_MODEL, input=question)["embeddings"][0]
    res = col.query(query_embeddings=[qe], n_results=min(k, col.count()))
    return [
        {"text": d, "page": m["page"], "filename": m["filename"], "score": round(1 - dist, 3)}
        for d, m, dist in zip(res["documents"][0], res["metadatas"][0], res["distances"][0])
    ]


def sse(obj: dict) -> str:
    return f"data: {json.dumps(obj)}\n\n"


def stream_answer(user_id: int, question: str, model: str | None):
    model = model or LLM_MODEL
    start = time.perf_counter()
    try:
        sources = retrieve(user_id, question)
        if not sources:
            yield sse({"type": "token", "text": "No documents indexed yet. Upload one first."})
            yield sse({"type": "done", "stats": {}})
            return
        yield sse({"type": "sources", "sources": sources})

        ctx = "\n\n".join(f"[{s['filename']} p{s['page']}] {s['text']}" for s in sources)
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Context:\n{ctx}\n\nQuestion: {question}"},
        ]
        first, tokens = None, 0
        for part in llm.chat(model=model, messages=messages, stream=True):
            piece = part["message"]["content"]
            if piece:
                if first is None:
                    first = time.perf_counter() - start
                tokens += 1
                yield sse({"type": "token", "text": piece})
        total = time.perf_counter() - start
        gen_time = max(total - (first or 0), 1e-6)
        yield sse({
            "type": "done",
            "stats": {
                "model": model,
                "time_to_first_token_s": round(first or 0, 2),
                "total_s": round(total, 2),
                "tokens": tokens,
                "tokens_per_s": round(tokens / gen_time, 1),
            },
        })
    except Exception as e:  # noqa: BLE001
        yield sse({"type": "error", "message": f"{type(e).__name__}: {e}"})
