import os
import httpx
from typing import List

MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY", "")
EMBED_MODEL = "mistral-embed"

async def get_embeddings(texts: List[str]) -> List[List[float]]:
    """Get embeddings from Mistral for a list of texts."""
    if not MISTRAL_API_KEY:
        raise RuntimeError("MISTRAL_API_KEY not set")
    
    # Mistral allows up to 16384 tokens per batch; batch in chunks of 32
    BATCH = 32
    all_embeddings = []
    
    async with httpx.AsyncClient(timeout=60) as client:
        for i in range(0, len(texts), BATCH):
            batch = texts[i : i + BATCH]
            resp = await client.post(
                "https://api.mistral.ai/v1/embeddings",
                headers={
                    "Authorization": f"Bearer {MISTRAL_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={"model": EMBED_MODEL, "input": batch},
            )
            resp.raise_for_status()
            data = resp.json()
            all_embeddings.extend([item["embedding"] for item in data["data"]])
    
    return all_embeddings

async def get_query_embedding(query: str) -> List[float]:
    """Get a single query embedding."""
    embs = await get_embeddings([query])
    return embs[0]
