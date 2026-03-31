import os
import hashlib
import hmac
import base64
import json
import time
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from db import get_db

SECRET_KEY = os.getenv("SECRET_KEY", "change-me-in-production-please")
TOKEN_TTL  = 60 * 60 * 24 * 7   # 7 days

bearer = HTTPBearer()

# ── Simple PBKDF2 password hashing (no extra deps) ─────────
def hash_password(password: str) -> str:
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), SECRET_KEY.encode(), 260_000)
    return base64.b64encode(dk).decode()

def verify_password(password: str, hashed: str) -> bool:
    return hmac.compare_digest(hash_password(password), hashed)

# ── Minimal JWT (HS256) without PyJWT ──────────────────────
def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()

def _sign(msg: str) -> str:
    return _b64url(hmac.new(SECRET_KEY.encode(), msg.encode(), hashlib.sha256).digest())

def create_token(user_id: int, username: str) -> str:
    header  = _b64url(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    payload = _b64url(json.dumps({
        "sub": user_id,
        "usr": username,
        "exp": int(time.time()) + TOKEN_TTL,
    }).encode())
    sig = _sign(f"{header}.{payload}")
    return f"{header}.{payload}.{sig}"

def decode_token(token: str) -> dict:
    try:
        header, payload, sig = token.split(".")
        if not hmac.compare_digest(_sign(f"{header}.{payload}"), sig):
            raise ValueError("bad signature")
        data = json.loads(base64.urlsafe_b64decode(payload + "=="))
        if data["exp"] < time.time():
            raise ValueError("expired")
        return data
    except Exception:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token")

# ── FastAPI dependency ──────────────────────────────────────
async def current_user(creds: HTTPAuthorizationCredentials = Depends(bearer)) -> dict:
    return decode_token(creds.credentials)

# ── DB helpers ──────────────────────────────────────────────
async def register_user(username: str, password: str) -> dict:
    async with get_db() as conn:
        existing = await conn.fetchrow("SELECT id FROM users WHERE username=$1", username)
        if existing:
            raise HTTPException(400, "Username already taken")
        hashed = hash_password(password)
        row = await conn.fetchrow(
            "INSERT INTO users (username, password_hash) VALUES ($1,$2) RETURNING id, username",
            username, hashed
        )
        token = create_token(row["id"], row["username"])
        return {"token": token, "username": row["username"], "user_id": row["id"]}

async def login_user(username: str, password: str) -> dict:
    async with get_db() as conn:
        row = await conn.fetchrow(
            "SELECT id, username, password_hash FROM users WHERE username=$1", username
        )
        if not row or not verify_password(password, row["password_hash"]):
            raise HTTPException(401, "Invalid credentials")
        token = create_token(row["id"], row["username"])
        return {"token": token, "username": row["username"], "user_id": row["id"]}
