import shutil
import uuid
from pathlib import Path

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session

from . import rag
from .auth import create_token, current_user, hash_password, verify_password
from .config import ALLOWED_EXT, LLM_MODEL, UPLOAD_DIR
from .db import Document, User, get_db

app = FastAPI(title="DocMind AI")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class Creds(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6)


class ChatIn(BaseModel):
    question: str = Field(min_length=1)
    model: str | None = None


def doc_out(d: Document) -> dict:
    return {
        "id": d.id, "filename": d.filename, "status": d.status, "error": d.error,
        "summary": d.summary, "chunks": d.chunks,
    }


@app.get("/api/health")
def health():
    return {"ok": True}


@app.post("/api/register")
def register(c: Creds, db: Session = Depends(get_db)):
    if db.query(User).filter(User.email == c.email.lower()).first():
        raise HTTPException(400, "Email already registered")
    u = User(email=c.email.lower(), password_hash=hash_password(c.password))
    db.add(u)
    db.commit()
    return {"token": create_token(u.id), "email": u.email}


@app.post("/api/login")
def login(c: Creds, db: Session = Depends(get_db)):
    u = db.query(User).filter(User.email == c.email.lower()).first()
    if not u or not verify_password(c.password, u.password_hash):
        raise HTTPException(401, "Wrong email or password")
    return {"token": create_token(u.id), "email": u.email}


@app.get("/api/documents")
def list_documents(user: User = Depends(current_user), db: Session = Depends(get_db)):
    docs = db.query(Document).filter(Document.user_id == user.id).order_by(Document.id.desc()).all()
    return [doc_out(d) for d in docs]


@app.post("/api/documents")
def upload(
    file: UploadFile,
    bg: BackgroundTasks,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    ext = Path(file.filename or "").suffix.lower()
    if ext not in ALLOWED_EXT:
        raise HTTPException(400, f"Unsupported file type. Allowed: {', '.join(sorted(ALLOWED_EXT))}")
    safe = f"{uuid.uuid4().hex}{ext}"
    path = UPLOAD_DIR / safe
    with open(path, "wb") as f:
        shutil.copyfileobj(file.file, f)
    doc = Document(user_id=user.id, filename=Path(file.filename).name, path=str(path))
    db.add(doc)
    db.commit()
    db.refresh(doc)
    bg.add_task(rag.ingest_document, doc.id)
    return doc_out(doc)


@app.delete("/api/documents/{doc_id}")
def delete_document(doc_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    doc = db.get(Document, doc_id)
    if not doc or doc.user_id != user.id:
        raise HTTPException(404, "Not found")
    rag.delete_document_vectors(user.id, doc.id)
    Path(doc.path).unlink(missing_ok=True)
    db.delete(doc)
    db.commit()
    return {"deleted": doc_id}


@app.get("/api/models")
def models(user: User = Depends(current_user)):
    try:
        names = [m["model"] for m in rag.llm.list()["models"]]
        names = [n for n in names if "embed" not in n]
    except Exception:
        names = []
    return {"default": LLM_MODEL, "models": names or [LLM_MODEL]}


@app.post("/api/chat")
def chat(body: ChatIn, user: User = Depends(current_user)):
    return StreamingResponse(
        rag.stream_answer(user.id, body.question, body.model),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
