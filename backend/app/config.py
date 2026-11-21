import os
from pathlib import Path

DATA_DIR = Path(os.getenv("DATA_DIR", "data"))
UPLOAD_DIR = DATA_DIR / "uploads"
CHROMA_DIR = DATA_DIR / "chroma"
for d in (DATA_DIR, UPLOAD_DIR, CHROMA_DIR):
    d.mkdir(parents=True, exist_ok=True)

OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
LLM_MODEL = os.getenv("LLM_MODEL", "llama3.2:3b")
EMBED_MODEL = os.getenv("EMBED_MODEL", "nomic-embed-text")

# Change this in production (set SECRET_KEY env var).
SECRET_KEY = os.getenv("SECRET_KEY", "change-me-in-production-please-use-32-chars-min")
TOKEN_HOURS = 24 * 7

CHUNK_SIZE = 800
CHUNK_OVERLAP = 150
TOP_K = 4
ALLOWED_EXT = {".pdf", ".docx", ".txt", ".md"}
