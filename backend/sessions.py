from db import get_db
from typing import List, Optional

async def create_session(user_id: int, title: str = "New Chat") -> dict:
    async with get_db() as conn:
        row = await conn.fetchrow(
            "INSERT INTO chat_sessions (user_id, title) VALUES ($1,$2) RETURNING id, title, created_at",
            user_id, title
        )
        return dict(row)

async def list_sessions(user_id: int) -> List[dict]:
    async with get_db() as conn:
        rows = await conn.fetch(
            """SELECT id, title, updated_at FROM chat_sessions
               WHERE user_id=$1 ORDER BY updated_at DESC""",
            user_id
        )
        return [dict(r) for r in rows]

async def get_session_messages(session_id: int, user_id: int) -> List[dict]:
    async with get_db() as conn:
        # verify ownership
        sess = await conn.fetchrow(
            "SELECT id FROM chat_sessions WHERE id=$1 AND user_id=$2",
            session_id, user_id
        )
        if not sess:
            return []
        rows = await conn.fetch(
            "SELECT role, content, sources FROM chat_messages WHERE session_id=$1 ORDER BY id",
            session_id
        )
        return [{"role": r["role"], "content": r["content"], "sources": list(r["sources"] or [])} for r in rows]

async def save_message(session_id: int, role: str, content: str, sources: List[str] = []):
    async with get_db() as conn:
        await conn.execute(
            "INSERT INTO chat_messages (session_id, role, content, sources) VALUES ($1,$2,$3,$4)",
            session_id, role, content, sources
        )
        # Auto-generate title from first user message
        if role == "user":
            count = await conn.fetchval(
                "SELECT COUNT(*) FROM chat_messages WHERE session_id=$1 AND role='user'", session_id
            )
            if count == 1:
                title = content[:60] + ("…" if len(content) > 60 else "")
                await conn.execute(
                    "UPDATE chat_sessions SET title=$1, updated_at=NOW() WHERE id=$2",
                    title, session_id
                )
            else:
                await conn.execute(
                    "UPDATE chat_sessions SET updated_at=NOW() WHERE id=$1", session_id
                )

async def delete_session(session_id: int, user_id: int):
    async with get_db() as conn:
        await conn.execute(
            "DELETE FROM chat_sessions WHERE id=$1 AND user_id=$2", session_id, user_id
        )
