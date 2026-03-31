import os
import json
import httpx
from typing import List, Tuple, AsyncGenerator

from db import get_db
from embeddings import get_query_embedding

MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY", "")
CHAT_MODEL = "mistral-large-latest"
TOP_K = 5

SYSTEM_PROMPT = """You are a helpful AI assistant with access to a knowledge base of documents.
When answering, use ONLY the provided context. If the context doesn't contain enough information, say so clearly.
Be concise, accurate, and cite which document sections informed your answer when relevant.
"""

async def retrieve_context(query: str, user_id: int) -> Tuple[List[str], List[str]]:
    query_emb = await get_query_embedding(query)
    emb_str = f"[{','.join(str(v) for v in query_emb)}]"

    async with get_db() as conn:
        rows = await conn.fetch(
            """
            SELECT content, source_file,
                   1 - (embedding <=> $1::vector) AS similarity
            FROM document_chunks
            WHERE user_id = $3
            ORDER BY embedding <=> $1::vector
            LIMIT $2
            """,
            emb_str, TOP_K, user_id
        )

    contents = [r["content"] for r in rows]
    sources  = list(dict.fromkeys(r["source_file"] for r in rows))
    return contents, sources

def _build_messages(message: str, history: List[dict], context_block: str) -> List[dict]:
    messages = [{
        "role": "system",
        "content": SYSTEM_PROMPT + f"\n\n## Relevant Context\n\n{context_block}"
    }]
    for turn in history[-6:]:
        messages.append({"role": turn["role"], "content": turn["content"]})
    messages.append({"role": "user", "content": message})
    return messages

async def rag_stream(
    message: str,
    history: List[dict],
    user_id: int
) -> AsyncGenerator[str, None]:
    """
    SSE generator. Protocol:
      data: {"type":"sources","sources":[...]}
      data: {"type":"delta","text":"..."}
      data: {"type":"done"}
    """
    if not MISTRAL_API_KEY:
        yield f'data: {json.dumps({"type":"error","msg":"MISTRAL_API_KEY not set"})}\n\n'
        return

    chunks, sources = await retrieve_context(message, user_id)
    context_block = (
        "\n\n---\n\n".join(
            f"[Source: {sources[min(i, len(sources)-1)]}]\n{chunk}"
            for i, chunk in enumerate(chunks)
        ) if chunks else "No documents uploaded yet."
    )

    yield f'data: {json.dumps({"type":"sources","sources":sources})}\n\n'

    messages = _build_messages(message, history, context_block)

    async with httpx.AsyncClient(timeout=120) as client:
        async with client.stream(
            "POST",
            "https://api.mistral.ai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {MISTRAL_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": CHAT_MODEL,
                "messages": messages,
                "temperature": 0.3,
                "max_tokens": 1024,
                "stream": True,
            },
        ) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line.startswith("data:"):
                    continue
                raw = line[5:].strip()
                if raw == "[DONE]":
                    break
                try:
                    data = json.loads(raw)
                    delta = data["choices"][0]["delta"].get("content", "")
                    if delta:
                        yield f'data: {json.dumps({"type":"delta","text":delta})}\n\n'
                except Exception:
                    continue

    yield f'data: {json.dumps({"type":"done"})}\n\n'
