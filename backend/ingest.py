import io
import re
from typing import List

import pdfplumber
from docx import Document as DocxDocument

from db import get_db
from embeddings import get_embeddings

CHUNK_SIZE = 512
CHUNK_OVERLAP = 64

def chunk_text(text: str, size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> List[str]:
    words = text.split()
    chunks = []
    start = 0
    while start < len(words):
        end = min(start + size, len(words))
        chunk = " ".join(words[start:end])
        if chunk.strip():
            chunks.append(chunk.strip())
        if end == len(words):
            break
        start += size - overlap
    return chunks

def extract_text(content: bytes, content_type: str) -> str:
    if content_type == "application/pdf":
        parts = []
        with pdfplumber.open(io.BytesIO(content)) as pdf:
            for page in pdf.pages:
                t = page.extract_text()
                if t:
                    parts.append(t)
        return "\n".join(parts)
    elif content_type in (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/msword"
    ):
        doc = DocxDocument(io.BytesIO(content))
        return "\n".join(p.text for p in doc.paragraphs if p.text.strip())
    else:
        return content.decode("utf-8", errors="replace")

async def ingest_document(content: bytes, filename: str, content_type: str, user_id: int) -> str:
    text = extract_text(content, content_type)
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        raise ValueError("Could not extract text from document")

    chunks = chunk_text(text)
    embeddings = await get_embeddings(chunks)

    async with get_db() as conn:
        await conn.execute(
            "DELETE FROM document_chunks WHERE source_file=$1 AND user_id=$2", filename, user_id
        )
        await conn.executemany(
            """
            INSERT INTO document_chunks (user_id, source_file, chunk_index, content, embedding)
            VALUES ($1, $2, $3, $4, $5::vector)
            """,
            [
                (user_id, filename, i, chunk, f"[{','.join(str(v) for v in emb)}]")
                for i, (chunk, emb) in enumerate(zip(chunks, embeddings))
            ]
        )

    print(f"✅ Ingested {filename} for user {user_id}: {len(chunks)} chunks")
    return filename
