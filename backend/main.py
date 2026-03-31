from fastapi import FastAPI, UploadFile, File, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import List, Optional
import uvicorn

from db import init_db
from ingest import ingest_document
from chat import rag_stream
from auth import current_user, register_user, login_user
from sessions import (
    create_session, list_sessions, get_session_messages,
    save_message, delete_session
)

app = FastAPI(title="RAG Mistral API")

app.add_middleware(
    CORSMiddleware,
    allow_origins = ["http://localhost:5173", "http://localhost:5174"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def startup():
    await init_db()

# ── Auth ─────────────────────────────────────────────────────
class AuthRequest(BaseModel):
    username: str
    password: str

@app.post("/auth/register")
async def register(req: AuthRequest):
    return await register_user(req.username, req.password)

@app.post("/auth/login")
async def login(req: AuthRequest):
    return await login_user(req.username, req.password)

@app.get("/auth/me")
async def me(user=Depends(current_user)):
    return {"user_id": user["sub"], "username": user["usr"]}

# ── Sessions ─────────────────────────────────────────────────
@app.post("/sessions")
async def new_session(user=Depends(current_user)):
    return await create_session(user["sub"])

@app.get("/sessions")
async def get_sessions(user=Depends(current_user)):
    return {"sessions": await list_sessions(user["sub"])}

@app.get("/sessions/{session_id}/messages")
async def session_messages(session_id: int, user=Depends(current_user)):
    msgs = await get_session_messages(session_id, user["sub"])
    return {"messages": msgs}

@app.delete("/sessions/{session_id}")
async def remove_session(session_id: int, user=Depends(current_user)):
    await delete_session(session_id, user["sub"])
    return {"status": "deleted"}

# ── Chat (streaming SSE) ──────────────────────────────────────
class ChatRequest(BaseModel):
    message: str
    session_id: int
    history: Optional[List[dict]] = []

@app.post("/chat")
async def chat(req: ChatRequest, user=Depends(current_user)):
    user_id = user["sub"]

    # Persist user message
    await save_message(req.session_id, "user", req.message)

    full_reply = []
    reply_sources = []

    async def event_stream():
        async for chunk in rag_stream(req.message, req.history, user_id):
            yield chunk
            # Collect for persistence
            if chunk.startswith("data:"):
                import json
                try:
                    d = json.loads(chunk[5:].strip())
                    if d["type"] == "delta":
                        full_reply.append(d["text"])
                    elif d["type"] == "sources":
                        reply_sources.extend(d["sources"])
                    elif d["type"] == "done":
                        # Persist assistant message after stream completes
                        await save_message(
                            req.session_id, "assistant",
                            "".join(full_reply), reply_sources
                        )
                except Exception:
                    pass

    return StreamingResponse(event_stream(), media_type="text/event-stream")

# ── Documents (user-scoped) ──────────────────────────────────
@app.post("/upload")
async def upload_document(
    file: UploadFile = File(...),
    user=Depends(current_user)
):
    allowed = ["application/pdf", "text/plain", "application/msword",
               "application/vnd.openxmlformats-officedocument.wordprocessingml.document"]
    if file.content_type not in allowed:
        raise HTTPException(400, "Only PDF, TXT, DOC, DOCX supported")
    content = await file.read()
    await ingest_document(content, file.filename, file.content_type, user["sub"])
    return {"filename": file.filename, "status": "ingested"}

@app.get("/documents")
async def list_documents(user=Depends(current_user)):
    from db import get_db
    async with get_db() as conn:
        rows = await conn.fetch(
            "SELECT DISTINCT source_file FROM document_chunks WHERE user_id=$1 ORDER BY source_file",
            user["sub"]
        )
        return {"documents": [r["source_file"] for r in rows]}

@app.delete("/documents/{filename}")
async def delete_document(filename: str, user=Depends(current_user)):
    from db import get_db
    async with get_db() as conn:
        await conn.execute(
            "DELETE FROM document_chunks WHERE source_file=$1 AND user_id=$2",
            filename, user["sub"]
        )
    return {"status": "deleted", "filename": filename}

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8001, reload=True)
