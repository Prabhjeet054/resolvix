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

6. **Launch the Streamlit app:**
   ```bash
   streamlit run app/streamlit_app.py
   ```

## Project Structure

```
├── db/              # SQL DDL/DML scripts and connection module
├── embeddings/      # Embedding generation and data ingestion
├── app/             # Streamlit frontend
├── data/            # Sample seed data (CSV)
├── tests/           # Unit tests
├── scripts/         # Utility scripts
```
