# Enterprise AI — multi-tenant RAG (Python only)

No React / TypeScript. FastAPI serves the API and a Jinja + vanilla JS portal.

## Run locally

```bash
cd enterprise-ai/backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cd ..
cp .env.example .env   # already present
cd backend && uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

Open http://localhost:8000

Demo tenants: **wipro**, **tcs**, **infosys**  
Users: `admin@wipro.com` / `Password@123` (also `emp@`, `hr@`, `finance@`)  
Platform: `admin@ent-ai.local` / `Admin@12345` (tenant `platform`)

Optional Groq: set `GROQ_API_KEY` for LLaMA 3.1 70B. Without a key the assistant answers from retrieved chunks only.

## Isolation

Every SQL query is tenant-scoped. Chroma collections are per-tenant namespaces and each chunk stores `tenant_id` + `access_level`.

## Docker

`docker compose up --build`
