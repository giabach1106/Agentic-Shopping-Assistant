# Agentic-Shopping-Assistant

## Backend Agent Core (Sprint 1)

### Option A: Python `venv` (recommended)

```bash
python -m venv .venv
# Windows PowerShell
.venv\Scripts\Activate.ps1
# macOS/Linux
# source .venv/bin/activate

python -m pip install -r backend/requirements.txt
cd backend
uvicorn app.main:app --reload
```

### Option B: Conda

```bash
conda create -n agent-shop python=3.12 -y
conda activate agent-shop
python -m pip install -r backend/requirements.txt
cd backend
uvicorn app.main:app --reload
```

### Option C: Docker (backend + Redis)

```bash
docker compose up --build
```

This starts:
- `backend` at `http://127.0.0.1:8000`
- `redis` at `localhost:6379`

### Test with CLI chatbot

```bash
# run from backend/
python scripts/chat_cli.py
```

Optional: pass existing session id.

```bash
python scripts/chat_cli.py --session-id <SESSION_ID>
```

### Run tests

```bash
cd backend
pytest -q
```

### Notes

- If Redis is not running locally, backend will fall back to in-memory checkpoints and show a warning at startup.
- To remove that warning in local non-docker mode, run Redis and set `AGENT_REDIS_URL=redis://localhost:6379/0`.
- RAG defaults to `inmemory` for local development. Set `RAG_BACKEND=bedrock_kb` and `BEDROCK_KB_ID=<your_kb_id>` to use Bedrock Knowledge Bases.
