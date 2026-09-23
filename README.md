# Ticket Similarity Finder

A multilingual support-ticket resolution assistant that uses Oracle AI Vector Search and semantic similarity to find previously resolved tickets matching a new query. Built with Oracle Database 23ai Free, Python 3.11, sentence-transformers (paraphrase-multilingual-MiniLM-L12-v2, 384-dim embeddings), and a Streamlit frontend. Support agents can search across tickets in multiple languages and instantly surface the most relevant past resolutions.

## Setup

1. **Create a virtual environment and install dependencies:**
   ```bash
   python3.11 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

2. **Configure credentials:**
   ```bash
   cp .env.example .env
   # Edit .env with your Oracle DB credentials
   ```

3. **Start Oracle Database 23ai Free in Docker:**
   ```bash
   docker run -d --name oracle23ai \
     -p 1521:1521 \
     -e ORACLE_PWD=<your_password> \
     container-registry.oracle.com/database/free:latest
   ```

4. **Run DDL scripts to create the schema:**
   ```bash
   python scripts/run_all_ddl.py
   ```

5. **Seed the database with sample tickets:**
   ```bash
   python embeddings/ingest.py
   ```

6. **Launch the shared web UI (FastAPI):**
   ```bash
   uvicorn api.main:app --host 127.0.0.1 --port 8080
   ```
   Open http://127.0.0.1:8080

7. **Or launch the desktop app (Electron):**
   ```bash
   cd electron
   npm install
   npm start
   ```
   Electron auto-starts the Python API and opens the same UI. See [electron/README.md](electron/README.md).

8. **Optional — Streamlit demo:**
   ```bash
   streamlit run app/streamlit_app.py
   ```

## Desktop app

Resolvix ships a downloadable Electron shell in [`electron/`](electron/) that:

- Starts `uvicorn api.main:app` from your local Python `.venv`
- Loads the shared frontend from [`frontend/`](frontend/) (same UI as the browser)

Build installers with `npm run dist:mac` / `dist:win` / `dist:linux` inside `electron/`.

## Project Structure

```
├── api/             # FastAPI backend (resolve, status, tickets, static UI)
├── frontend/        # Shared web UI (browser + Electron)
├── electron/        # Electron desktop shell (auto-starts Python API)
├── db/              # SQL DDL/DML scripts and connection module
├── embeddings/      # Embedding generation and data ingestion
├── agent/           # Ollama agent pipeline
├── app/             # Streamlit frontend (optional demo)
├── data/            # Sample seed data (CSV)
├── tests/           # Unit tests
├── scripts/         # Utility scripts
```
