# Sapien — RAG Chatbot with Mistral AI + pgvector

A full-stack Retrieval-Augmented Generation (RAG) chatbot.  
Upload PDFs/docs → ask questions → get answers grounded in your documents.

## Stack

| Layer      | Tech                              |
|------------|-----------------------------------|
| LLM        | `mistral-large-latest`            |
| Embeddings | `mistral-embed` (1024 dims)       |
| Vector DB  | PostgreSQL + pgvector (IVFFlat)   |
| Backend    | FastAPI + asyncpg                 |
| Frontend   | React + Vite                      |
| Parsing    | pdfplumber, python-docx           |

## Quick Start

### 1. Clone & configure
```bash
git clone <your-repo>
cd rag-mistral

cp backend/.env.example backend/.env
# Edit .env and set MISTRAL_API_KEY
```

### 2. Start with Docker Compose
```bash
MISTRAL_API_KEY=your_key docker-compose up --build
```

- Frontend: http://localhost:5173  
- API docs: http://localhost:8000/docs

### 3. Or run manually

**Database (pgvector)**
```bash
docker run -d \
  -e POSTGRES_DB=ragdb \
  -e POSTGRES_USER=postgres \
  -e POSTGRES_PASSWORD=postgres \
  -p 5432:5432 \
  pgvector/pgvector:pg16
```

**Backend**
```bash
cd backend
pip install -r requirements.txt
cp .env.example .env   # fill in MISTRAL_API_KEY
uvicorn main:app --reload
```

**Frontend**
```bash
cd frontend
npm install
npm run dev
```

## How RAG Works Here

```
User question
    │
    ▼
mistral-embed (query embedding)
    │
    ▼
pgvector cosine similarity search → top 5 chunks
    │
    ▼
Chunks injected into system prompt
    │
    ▼
mistral-large-latest generates grounded answer
    │
    ▼
Response + source filenames returned
```

## API Endpoints

| Method | Path                    | Description                  |
|--------|-------------------------|------------------------------|
| POST   | `/upload`               | Upload PDF/TXT/DOCX          |
| POST   | `/chat`                 | Chat with RAG context        |
| GET    | `/documents`            | List ingested documents      |
| DELETE | `/documents/{filename}` | Remove a document            |
| GET    | `/docs`                 | FastAPI Swagger UI           |

## Configuration

| Env var        | Default                                         |
|----------------|-------------------------------------------------|
| MISTRAL_API_KEY | (required)                                     |
| DATABASE_URL   | postgresql://postgres:postgres@localhost:5432/ragdb |

## Tuning

- **Chunk size**: `CHUNK_SIZE` in `ingest.py` (default 512 words)  
- **Chunk overlap**: `CHUNK_OVERLAP` (default 64 words)  
- **Top-K retrieval**: `TOP_K` in `chat.py` (default 5 chunks)  
- **Temperature**: 0.3 in `chat.py` (lower = more faithful to context)
