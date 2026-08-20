# Cursor Prompts — Multilingual Support-Ticket Similarity Finder

Project context to paste into Cursor's rules/notepad once (or repeat in your first prompt) so every subsequent prompt has shared context:

> **Project:** Multilingual Support-Ticket Resolution Assistant using Oracle AI Vector Search and Semantic Similarity.
> **Stack:** Oracle Database 23ai Free (Docker), Python 3.11, `oracledb` driver, `sentence-transformers` (model: `paraphrase-multilingual-MiniLM-L12-v2`, 384-dim embeddings), Streamlit frontend.
> **DB schema (target):** Customers, Agents, Categories, Tickets (with JSON metadata column and VECTOR(384, FLOAT32) embedding column).
> **Credentials:** Never hardcode — always read from `.env` via `python-dotenv`.
> **Style:** Add docstrings/comments, use `snake_case` for tables/columns, wrap SQL execution in try/except with rollback on failure, close cursors/connections properly (use context managers where possible).

---

## 1. Project scaffolding

**Prompt:**
```
Create the full folder structure for a Python project called "ticket-similarity-finder":
- /db          → holds .sql DDL/DML scripts, organized as 01_customers.sql, 02_agents.sql, 03_categories.sql, 04_tickets.sql, 05_views.sql, 06_indexes.sql, etc. (numbered so execution order is clear)
- /embeddings  → generate.py (embedding generation logic), ingest.py (loads CSV, generates embeddings, inserts into DB)
- /app         → streamlit_app.py (frontend)
- /data        → tickets_seed.csv (sample multilingual dataset)
- /tests       → one test file per major component (test_connection.py, test_embeddings.py, test_similarity_query.py)
- /scripts     → utility scripts like run_all_ddl.py (executes all .sql files in /db in order)

Also create:
- .env.example with placeholders: ORACLE_USER=, ORACLE_PASSWORD=, ORACLE_DSN=localhost:1521/FREEPDB1
- .gitignore excluding .env, __pycache__, .venv, *.pyc, .DS_Store
- requirements.txt pinning: oracledb, sentence-transformers, streamlit, python-dotenv, pandas, numpy
- README.md with a one-paragraph project description, setup steps (create venv, pip install, copy .env.example to .env, start Docker, run scripts/run_all_ddl.py), and a placeholder "Usage" section
- A simple db/connection.py module with a get_connection() function that reads credentials from .env using python-dotenv and returns an oracledb connection object, with proper error handling if env vars are missing

Print the final folder tree after creating it.
```

**Testing prompt:**
```
Write and run a smoke-test script tests/test_structure.py that:
1. Asserts all expected folders (db, embeddings, app, data, tests, scripts) exist
2. Asserts .env.example, requirements.txt, README.md, .gitignore exist
3. Asserts db/connection.py exports a callable get_connection
Run it with pytest and show me the output. Also run `pip install -r requirements.txt` inside a fresh virtual environment named .venv and confirm zero errors, then print `pip list` filtered to only the packages we specified.
```

---

## 2. Oracle 23ai Docker setup

**Prompt:**
```
Write a docker-compose.yml in the project root that runs Oracle Database 23ai Free with these requirements:
- Image: container-registry.oracle.com/database/free:latest (note this explicitly in a comment, and add a fallback comment mentioning gvenzl/oracle-free as an alternative if the official image has pull issues)
- Container name: ticket-oracle-db
- Port mapping: 1521:1521 and 5500:5500 (EM Express)
- Environment variables for ORACLE_PWD sourced from .env (use env_file directive pointing to .env)
- A named Docker volume "oracle_data" mounted to /opt/oracle/oradata for persistence
- A healthcheck that checks the DB is ready (using a shell command appropriate for the Oracle Free image, e.g. checking the alert log or using sqlplus ping)
- restart: unless-stopped

Also write a short docs/DOCKER_SETUP.md explaining:
1. Minimum system requirements (RAM/disk) for Oracle 23ai Free
2. Exact commands to pull, start, check logs, and stop the container
3. How long first startup typically takes and what log line to watch for indicating "database is ready"
4. Troubleshooting section for common failures (port already in use, insufficient memory, ARM architecture issues on Apple Silicon) with the fallback gvenzl/oracle-free image as Plan B
```

**Testing prompt:**
```
Write tests/test_connection.py using the oracledb driver that:
1. Loads credentials from .env via python-dotenv
2. Connects to the DB using db/connection.py's get_connection()
3. Runs "SELECT 1 FROM dual" and asserts the result is 1
4. Runs "SELECT banner FROM v$version WHERE ROWNUM = 1" and prints the Oracle version string, asserting it contains "23"
5. Closes the connection cleanly in a finally block
Run `docker compose up -d`, wait for the healthcheck to pass (poll docker inspect for health status, timeout after 5 minutes with a clear error if it never becomes healthy), then run this test and show me the full output including the printed Oracle version.
```

---

## 3. Customers, Agents, Categories DDL

**Prompt:**
```
Write db/01_customers.sql, db/02_agents.sql, db/03_categories.sql with the following exact schema requirements:

Customers:
- customer_id NUMBER, PRIMARY KEY
- customer_name VARCHAR2(150) NOT NULL
- email VARCHAR2(150) NOT NULL, UNIQUE
- phone VARCHAR2(20)
- region VARCHAR2(50)   -- e.g. IN, US, UK — used later for timezone demo
- created_at TIMESTAMP DEFAULT SYSTIMESTAMP

Agents:
- agent_id NUMBER, PRIMARY KEY
- agent_name VARCHAR2(150) NOT NULL
- email VARCHAR2(150) NOT NULL, UNIQUE CONSTRAINT named explicitly (e.g. uq_agent_email)
- department VARCHAR2(100)
- is_active NUMBER(1) DEFAULT 1 CHECK (is_active IN (0,1))

Categories:
- category_id NUMBER, PRIMARY KEY
- category_name VARCHAR2(100) NOT NULL UNIQUE
- description VARCHAR2(300)

For every constraint, use explicit CONSTRAINT names (not system-generated) following the pattern pk_<table>, uq_<table>_<column>, ck_<table>_<column> — this matters for viva/report clarity when I later query USER_CONSTRAINTS.

Also write db/00_drop_all.sql that drops all these tables (with CASCADE CONSTRAINTS) in reverse dependency order, guarded with a PL/SQL block using EXCEPTION WHEN OTHERS so it doesn't fail if the tables don't exist yet — I'll use this for clean re-runs during development.
```

**Testing prompt:**
```
Write scripts/run_ddl_subset.py that connects via db/connection.py and executes 01_customers.sql, 02_agents.sql, 03_categories.sql in order (split multi-statement files correctly on ";" while ignoring semicolons inside PL/SQL blocks). After running, write and execute a verification query against USER_CONSTRAINTS and USER_CONS_COLUMNS that prints, for each of the 3 tables: the constraint name, constraint type (P/U/C), and column(s) involved. Confirm every constraint has the explicit name I specified rather than a SYS_C-prefixed auto-generated name.
```

---

## 4. Tickets table with FK, JSON, VECTOR

**Prompt:**
```
Write db/04_tickets.sql creating the Tickets table with this exact schema:
- ticket_id NUMBER, PRIMARY KEY (constraint name pk_tickets)
- customer_id NUMBER, FOREIGN KEY REFERENCES Customers(customer_id) (constraint name fk_tickets_customer)
- agent_id NUMBER, FOREIGN KEY REFERENCES Agents(agent_id), NULLABLE (a ticket may be unassigned) (constraint name fk_tickets_agent)
- category_id NUMBER, FOREIGN KEY REFERENCES Categories(category_id) (constraint name fk_tickets_category)
- description CLOB NOT NULL
- language_code VARCHAR2(5)   -- 'en', 'hi', 'ta' etc.
- ticket_status VARCHAR2(20) DEFAULT 'OPEN' CHECK (ticket_status IN ('OPEN','IN_PROGRESS','RESOLVED','CLOSED')) (constraint name ck_tickets_status)
- priority VARCHAR2(10) DEFAULT 'MEDIUM' CHECK (priority IN ('LOW','MEDIUM','HIGH','URGENT')) (constraint name ck_tickets_priority)
- created_date TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL
- resolved_date TIMESTAMP NULL
- resolution CLOB NULL
- metadata JSON NULL   -- for tags, attachment info
- description_embedding VECTOR(384, FLOAT32) NULL

Explain in a SQL comment at the top of the file why description_embedding is nullable (so we can insert ticket rows before running the embedding generation step, and backfill vectors afterward).

Also add a CHECK constraint ensuring resolved_date is NULL or >= created_date (constraint name ck_tickets_resolved_after_created).
```

**Testing prompt:**
```
Run db/04_tickets.sql via scripts/run_ddl_subset.py (extend it to accept a filename argument). Then write a verification script that:
1. Queries USER_CONS_COLUMNS joined with USER_CONSTRAINTS to list all 3 foreign keys on Tickets and confirm each references the correct parent table/column
2. Queries USER_TAB_COLUMNS for the Tickets table and confirms description_embedding has data_type showing as VECTOR
3. Attempts an INSERT that violates the ck_tickets_resolved_after_created constraint (resolved_date earlier than created_date) and confirms Oracle raises an error (catch and print the ORA error code/message, don't let the script crash)
4. Attempts an INSERT with a non-existent customer_id and confirms the FK constraint blocks it, printing the ORA error
```

---

## 5. Sequence + trigger for ticket_id

**Prompt:**
```
Write db/05_sequence_trigger.sql that:
1. Creates a sequence named ticket_seq, START WITH 1000, INCREMENT BY 1, NOCACHE (explain in a comment why NOCACHE is chosen here — for demo/predictability vs performance tradeoff)
2. Creates a BEFORE INSERT trigger named trg_tickets_id on the Tickets table that, for each row, checks IF :NEW.ticket_id IS NULL THEN sets :NEW.ticket_id := ticket_seq.NEXTVAL, otherwise leaves the provided value untouched (so tests can still insert explicit IDs when needed)
3. Includes a comment block above the trigger explaining that this pattern is used instead of Oracle 23ai's native IDENTITY column specifically because the syllabus requires demonstrating explicit sequence usage (Unit 4)
```

**Testing prompt:**
```
Write tests/test_sequence_trigger.py that:
1. Inserts 3 ticket rows without specifying ticket_id (only required NOT NULL fields: customer_id, category_id, description, created_date — use existing seeded customer/category IDs, insert temporary ones if none exist yet)
2. Queries back the 3 inserted rows ordered by insert order and asserts ticket_id values are strictly increasing and follow the sequence (no duplicates, no gaps unless expected)
3. Inserts one more row WITH an explicit ticket_id (e.g. 99999) and confirms that exact value was used, not overridden by the trigger
4. Cleans up (deletes) all 4 test rows at the end regardless of pass/fail, using a try/finally block
Print each assertion result clearly (PASS/FAIL with the actual values).
```

---

## 6. Seed data — Customers/Agents/Categories

**Prompt:**
```
Write embeddings/../db/seed_reference_data.py (place it in /scripts instead, name it seed_reference_data.py) that connects via db/connection.py and inserts:
- 10 sample customers with realistic Indian-context names, varied emails, and region values from {'IN','US','UK'} (at least 3 of each, roughly)
- 5 sample agents with names, unique emails, department values from {'Technical','Billing','General'}, is_active=1
- 6 categories: Billing, Technical, Account, Refund, Login, General — each with a short one-line description

Use parameterized queries (bind variables, not string formatting) to avoid SQL injection even though this is seed data — note in a comment that this is good practice to demonstrate in the report. Commit the transaction only after all inserts succeed; roll back entirely if any insert fails. Print a summary at the end: "Inserted X customers, Y agents, Z categories."
```

**Testing prompt:**
```
Run scripts/seed_reference_data.py once, then write tests/test_seed_data.py that:
1. Connects to the DB
2. Runs SELECT COUNT(*) on Customers, Agents, Categories and asserts counts are exactly 10, 5, 6
3. Runs a query grouping Customers by region and prints the breakdown
4. Confirms no duplicate emails exist in Customers (SELECT email, COUNT(*) ... HAVING COUNT(*) > 1 should return 0 rows) and same for Agents
Run the seed script a second time and confirm it fails cleanly with a clear unique-constraint violation message rather than silently inserting duplicates (this proves the UNIQUE constraints work end-to-end).
```

---

## 7. Multilingual ticket dataset

**Prompt:**
```
Create data/tickets_seed.csv with exactly 20 rows and these columns: description, language_code, category_name, resolution, priority.

Requirements:
- All 20 tickets must stay within the SAME general domain (software/billing/account support) so semantic similarity comparisons later are meaningful — do not mix in unrelated domains like "restaurant complaint" or "flight booking"
- Distribute languages roughly evenly: ~7 English (en), ~7 Hindi (hi, written in Devanagari script), ~6 Tamil (ta, written in Tamil script)
- Deliberately create at least 3 "translation pairs/triples" — i.e. the same underlying issue expressed independently in English, Hindi, and Tamil (e.g. "unable to reset my password" / hindi equivalent / tamil equivalent) so I can later validate that the embedding model correctly clusters them together despite different scripts
- Each row's resolution field should be a realistic 1-2 sentence fix a support agent would write
- Vary priority across LOW/MEDIUM/HIGH/URGENT realistically (most should be MEDIUM/HIGH, few URGENT)
- category_name values must exactly match the 6 categories already seeded: Billing, Technical, Account, Refund, Login, General

After creating the CSV, print it as a formatted table so I can visually verify the translation pairs line up correctly in meaning.
```

**Testing prompt:**
```
Write scripts/validate_seed_csv.py using pandas that:
1. Loads data/tickets_seed.csv and asserts it has exactly 20 rows and the 5 expected columns
2. Prints value_counts() for language_code and confirms all 3 languages are represented with none below 5 rows
3. Prints value_counts() for category_name and confirms every value is one of the 6 valid categories (fail loudly listing any invalid ones)
4. Prints value_counts() for priority and confirms all 4 priority levels appear at least once
5. Checks for and reports any completely empty description or resolution cells
Run it and show me the full output.
```

---

## 8. Embedding generation script

**Prompt:**
```
Write embeddings/generate.py with:
1. A module-level cached loader function get_model() that loads SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2') once and reuses it (avoid reloading the model on every call — use functools.lru_cache or a module-level singleton)
2. A function generate_embedding(text: str) -> np.ndarray that:
   - Strips/normalizes whitespace in the input text
   - Raises a ValueError with a clear message if text is empty or None
   - Encodes the text using the loaded model
   - Returns a numpy array of dtype float32 with shape (384,)
3. A function generate_embeddings_batch(texts: list[str]) -> np.ndarray for batch encoding multiple tickets at once (more efficient for ingestion), using the model's batch encode capability
4. Proper docstrings explaining that this model maps semantically similar text across languages (English/Hindi/Tamil) into nearby points in the same 384-dimensional vector space, which is why cross-lingual similarity search works
5. A __main__ block that, when run directly, encodes a sample sentence and prints its shape and dtype as a sanity check
```

**Testing prompt:**
```
Write tests/test_embeddings.py that:
1. Imports generate_embedding and asserts it returns shape (384,) and dtype float32 for a sample English sentence
2. Asserts calling generate_embedding("") or generate_embedding(None) raises ValueError
3. THE KEY TEST: takes one of the English/Hindi/Tamil translation-pair tickets from data/tickets_seed.csv (same meaning, different language), generates embeddings for all versions, computes cosine similarity between each pair (using numpy: dot(a,b)/(norm(a)*norm(b))), and asserts similarity > 0.7 for each cross-lingual pair
4. Also picks two UNRELATED tickets from the CSV (different category, different meaning) and asserts their cosine similarity is meaningfully lower (e.g. < 0.5) than the translation-pair similarity, to prove the model actually discriminates and isn't just returning uniformly high similarity
Print all computed similarity scores clearly labeled (which pair, which languages, the score) so I can include this as evidence in my report.
```

---

## 9. Ingestion script

**Prompt:**
```
Write embeddings/ingest.py that:
1. Loads data/tickets_seed.csv via pandas
2. For each row: looks up customer_id (round-robin assign from the 10 seeded customers), agent_id (round-robin assign from the 5 seeded agents, but leave ~20% of tickets with agent_id=NULL to simulate unassigned tickets), category_id (look up by category_name against the Categories table)
3. Randomly assigns ticket_status: mostly 'RESOLVED' or 'CLOSED' (since these are historical tickets with resolutions) but 2-3 should be 'OPEN' with no resolution/resolved_date (simulating new unresolved tickets for later demo)
4. For resolved tickets, generates a random resolved_date between created_date and created_date + 5 days, and created_date itself randomized within the last 90 days
5. Generates a metadata JSON object per ticket containing a "tags" array (1-3 relevant tags derived from category) and an "attachment_count" integer (0-2)
6. Calls embeddings/generate.py's generate_embedding() on the description text
7. Inserts each row into Tickets using oracledb's array/vector binding for the VECTOR column (research and use the correct oracledb API for binding a Python list/numpy array to a VECTOR column type — likely via db_type=oracledb.DB_TYPE_VECTOR or similar; look this up and implement it correctly)
8. Wraps the whole batch in a single transaction: commit only if ALL 20 rows insert successfully, otherwise rollback and print which row failed and why
9. Prints a progress indicator (e.g. "Inserted 5/20...") as it goes
```

**Testing prompt:**
```
Run embeddings/ingest.py, then write tests/test_ingestion.py that:
1. Asserts SELECT COUNT(*) FROM Tickets equals 20
2. Runs SELECT ticket_id, VECTOR_DIMENSION_COUNT(description_embedding) AS dim FROM Tickets and asserts every row returns dim = 384 with none NULL
3. Asserts at least 2 and at most 5 tickets have ticket_status = 'OPEN' (per the randomization rule)
4. Asserts every RESOLVED/CLOSED ticket has a non-null resolution and resolved_date >= created_date
5. Runs SELECT JSON_VALUE(metadata, '$.attachment_count') FROM Tickets WHERE ROWNUM <= 3 and confirms it returns valid integers (proving JSON was stored correctly)
6. Runs the ingestion script a second time on top of existing data and confirms it does NOT silently duplicate all 20 tickets (either by checking a description-uniqueness rule you add, or by explicitly truncating Tickets first in the script — pick one approach and document it)
```

---

## 10. Top-3 similarity query

**Prompt:**
```
Write embeddings/similarity_search.py with a function find_similar_tickets(query_embedding: np.ndarray, exclude_ticket_id: int = None, top_n: int = 3) -> list[dict] that:
1. Connects to the DB via db/connection.py
2. Builds and executes a parameterized SQL query using Oracle's VECTOR_DISTANCE(description_embedding, :query_vec, COSINE) function, ordering by that distance ascending (lower distance = more similar), limiting to top_n rows using FETCH FIRST :top_n ROWS ONLY
3. If exclude_ticket_id is provided, adds a WHERE ticket_id != :exclude_ticket_id clause so a ticket never matches itself
4. Only considers tickets with ticket_status IN ('RESOLVED','CLOSED') as candidates (no point suggesting an unresolved ticket as a "solution")
5. Returns a list of dicts, each containing: ticket_id, description (truncated to 200 chars), resolution, language_code, category_name (via join), similarity_distance (raw value), and similarity_score (1 - distance, as a friendlier 0-1 "closeness" number for display)
6. Handles the correct oracledb binding syntax for passing a numpy array as the :query_vec bind variable (same VECTOR binding approach used in ingest.py)
7. Include a docstring explaining that COSINE distance ranges 0 (identical direction) to 2 (opposite), and why COSINE is preferred over EUCLIDEAN for this multilingual text-embedding use case
```

**Testing prompt:**
```
Write tests/test_similarity_query.py that:
1. Picks one specific seeded ticket (e.g. the English "password reset" ticket), generates its embedding, calls find_similar_tickets excluding its own ticket_id
2. Asserts the returned list has length <= 3, and the ticket's own ticket_id never appears in results
3. Asserts results are ordered by similarity_score descending (most similar first)
4. THE KEY TEST: asserts that among the top-3 results, at least one is the Hindi or Tamil translation-pair ticket for that same issue (proving cross-lingual retrieval works end-to-end through the actual DB query, not just in isolated embedding tests)
5. Runs the same function against a brand-new, never-seeded query string (simulate a "new incoming ticket" by generating an embedding for a fresh sentence not in the CSV) and prints the top-3 results with their similarity scores for manual eyeballing
Print a clear PASS/FAIL summary table for each assertion.
```

---

## 11. Views for open tickets by priority

**Prompt:**
```
Write db/06_views.sql creating a view named high_priority_open_tickets that:
- Selects ticket_id, description (first 200 chars via SUBSTR), customer_name (joined from Customers), agent_name (joined from Agents, using a LEFT JOIN since agent_id can be NULL), category_name (joined from Categories), created_date, priority
- Filters WHERE ticket_status = 'OPEN' AND priority IN ('HIGH','URGENT')
- Orders by priority (URGENT before HIGH — use a CASE expression or DECODE for custom ordering) then created_date ascending (oldest first, since those need attention soonest)

Also create a second view named tickets_full_report that joins all 4 tables (Tickets, Customers, Agents, Categories) with no filtering, showing every column relevant for reporting — this will be reused in later group-function/join prompts so keep column naming clean and consistent (avoid ambiguous column names across the joined tables).
```

**Testing prompt:**
```
Write tests/test_views.py that:
1. Queries USER_VIEWS to confirm both high_priority_open_tickets and tickets_full_report exist
2. Inserts 2 temporary test tickets: one with status=OPEN, priority=URGENT (should appear in the view) and one with status=OPEN, priority=LOW (should NOT appear)
3. Queries high_priority_open_tickets and asserts the URGENT ticket is present and the LOW ticket is absent
4. Asserts the URGENT ticket appears before any HIGH-priority tickets in the result ordering (confirming the custom priority ordering works)
5. Queries tickets_full_report and asserts the row count matches the current Tickets table row count (proving the joins aren't dropping or duplicating rows, especially for tickets with NULL agent_id via the LEFT JOIN)
6. Cleans up the 2 temporary test tickets in a finally block
```

---

## 12. Indexes on status and created_date

**Prompt:**
```
Write db/07_indexes.sql creating:
1. A B-tree index idx_tickets_status on Tickets(ticket_status)
2. A B-tree index idx_tickets_created_date on Tickets(created_date)
3. A composite index idx_tickets_status_created on Tickets(ticket_status, created_date) — explain in a comment why a composite index can serve queries that filter on status AND sort/filter on created_date more efficiently than two separate single-column indexes

Also write scripts/explain_plan_demo.py that:
1. Runs EXPLAIN PLAN FOR SELECT * FROM Tickets WHERE ticket_status = 'OPEN' both BEFORE creating the indexes (temporarily, by dropping them if they exist first) and AFTER creating them
2. Queries PLAN_TABLE (or uses DBMS_XPLAN.DISPLAY) to print the execution plan in both cases
3. Prints a clear before/after comparison highlighting whether the plan changed from a full table scan to an index-based access path
```

**Testing prompt:**
```
Run scripts/explain_plan_demo.py and show me the full before/after EXPLAIN PLAN output. Then write tests/test_indexes.py that:
1. Queries USER_INDEXES to confirm all 3 indexes exist on the Tickets table with the correct index type (NORMAL)
2. Queries USER_IND_COLUMNS to confirm idx_tickets_status_created has exactly 2 columns in the correct order (ticket_status first, then created_date)
Note: since our Tickets table only has ~20 rows, the optimizer might still choose a full table scan regardless of indexes (Oracle's cost-based optimizer prefers full scans on tiny tables) — if that happens in the EXPLAIN PLAN test, explain this clearly in the output/report rather than treating it as a failure, and suggest inserting a few hundred dummy rows via a loop if I want to force the optimizer to demonstrate index usage for the report screenshots.
```

---

## 13. Group functions — tickets per agent, avg resolution time

**Prompt:**
```
Write db/08_reports_group_functions.sql containing two named, well-commented queries:
1. Query A: tickets per agent — SELECT agent_name, COUNT(*) AS ticket_count, ROUND(AVG(resolved_date - created_date), 2) AS avg_resolution_days FROM tickets_full_report (or joined directly) WHERE resolved_date IS NOT NULL GROUP BY agent_name ORDER BY ticket_count DESC. Handle the case of agent_id being NULL (unassigned tickets) by using a separate row labeled 'Unassigned' via NVL on agent_name.
2. Query B: tickets per category with priority breakdown — SELECT category_name, priority, COUNT(*) AS cnt FROM ... GROUP BY category_name, priority ORDER BY category_name, priority, using GROUPING SETS or just a plain GROUP BY (explain which you chose and why in a comment)

Also write scripts/run_reports.py that executes both queries and pretty-prints the results as formatted tables using Python (e.g. via tabulate or manual string formatting) so I can screenshot them for the report.
```

**Testing prompt:**
```
Write tests/test_group_functions.py that:
1. Runs Query A and manually recomputes the expected avg_resolution_days for ONE specific agent by pulling their raw resolved tickets directly (SELECT resolved_date, created_date WHERE agent_id = X) and computing the average in Python, then asserts it matches what Query A returned (within a small floating-point tolerance)
2. Asserts the sum of ticket_count across all agent rows in Query A (including the 'Unassigned' row) equals the total count of resolved tickets in the Tickets table
3. Runs Query B and asserts the sum of cnt across all rows equals the total ticket count in the Tickets table
Print both verification results clearly.
```

---

## 14. Subquery — resolution time above average

**Prompt:**
```
Write db/09_subquery_above_avg.sql with a query that returns ticket_id, description (truncated), agent_name, and resolution_days for all resolved tickets whose resolution time (resolved_date - created_date) is strictly greater than the average resolution time across ALL resolved tickets — implemented using a subquery in the WHERE clause: WHERE (resolved_date - created_date) > (SELECT AVG(resolved_date - created_date) FROM Tickets WHERE resolved_date IS NOT NULL).

Also write a second variant of the same query using a correlated subquery style or a WITH clause (CTE) instead, and add a comment explaining the difference between the two approaches (subquery in WHERE vs CTE) and when each is preferable for readability/performance.
```

**Testing prompt:**
```
Write tests/test_subquery.py that:
1. Independently computes the average resolution time in Python (pull all resolved tickets' created_date/resolved_date via a simple SELECT, compute average manually with Python's datetime arithmetic)
2. Runs the SQL subquery from db/09_subquery_above_avg.sql and asserts every returned row's resolution_days is strictly greater than the Python-computed average
3. Asserts the count of returned rows is less than the total count of resolved tickets (since not all tickets can be above average)
4. Confirms both query variants (subquery-in-WHERE and CTE) return identical result sets (same ticket_ids, same order or compare as sets)
```

---

## 15. Joins across Ticket-Customer-Agent

**Prompt:**
```
Write db/10_full_ticket_report_query.sql with a single well-formatted query joining Tickets, Customers, Agents, and Categories using explicit JOIN syntax (not old-style comma joins), demonstrating:
- INNER JOIN to Customers and Categories (every ticket must have these)
- LEFT OUTER JOIN to Agents (since agent_id can be NULL for unassigned tickets)
- Selecting: ticket_id, customer_name, NVL(agent_name, 'Unassigned') AS agent_name, category_name, ticket_status, priority, created_date, resolution
- Ordered by created_date DESC

Add a comment explaining explicitly why LEFT JOIN is required for Agents but INNER JOIN is fine for Customers/Categories, referencing the FK nullability from the schema design in prompt 4 — this is good material for a viva question about join types.
```

**Testing prompt:**
```
Write tests/test_joins.py that:
1. Runs the join query and asserts the row count exactly matches SELECT COUNT(*) FROM Tickets (proving no rows were dropped by the LEFT JOIN or duplicated by any join)
2. Specifically finds a ticket with NULL agent_id in the raw Tickets table, confirms it appears in the join query results with agent_name = 'Unassigned' (not silently dropped, which would happen if INNER JOIN were mistakenly used instead)
3. Cross-checks 3 random rows from the join output against manually querying each source table individually to confirm the joined values (customer_name, category_name) are correct and not mismatched
```

---

## 16. GRANT/REVOKE roles

**Prompt:**
```
Write db/11_roles_access_control.sql that:
1. Creates two Oracle roles: agent_role and admin_role
2. Creates a view my_tickets that filters Tickets WHERE agent_id = (SELECT agent_id FROM Agents WHERE email = SYS_CONTEXT('USERENV','SESSION_USER') -- explain in a comment that for a real multi-schema setup this would map DB users to agent emails, and for this project demo, document the simplified assumption being made (e.g. one shared app user with agent_id passed at the application layer instead, OR create actual per-agent DB users — pick the simpler, clearly documented approach given this is a college project, not production)
3. GRANTs SELECT, UPDATE on the my_tickets view (or the simplified equivalent) to agent_role
4. GRANTs SELECT on ALL 4 base tables (Tickets, Customers, Agents, Categories) plus INSERT/UPDATE/DELETE on Tickets to admin_role
5. Creates two actual test database users: test_agent_user and test_admin_user, sets temporary passwords (documented in a local-only, gitignored credentials file, not in the .sql file itself), and GRANTs the respective roles to each
6. Includes the exact REVOKE statements as a commented-out section at the bottom, ready to run, demonstrating how to remove access

Be explicit and pragmatic here — pick whichever access-control implementation is realistically demonstrable in Oracle 23ai Free within a college project timeframe, and clearly document the assumption in a comment block at the top of the file.
```

**Testing prompt:**
```
Write tests/test_access_control.py that:
1. Connects as test_admin_user and confirms they CAN SELECT from all 4 tables and CAN INSERT a test row into Tickets
2. Connects as test_agent_user and confirms they CAN SELECT from the my_tickets view but get an ORA-00942 or permission-denied error when attempting to SELECT directly from the Customers or Agents base tables (if that's part of the restriction design) — or confirms whatever the actual documented restriction is
3. Runs the REVOKE statements, then re-attempts the same operations as test_agent_user and confirms access is now denied where expected
4. Prints a clear before/after access matrix table (role x table x permission) summarizing what was tested, formatted for direct inclusion in my report
```

---

## 17. JSON metadata querying

**Prompt:**
```
Write db/12_json_queries.sql with:
1. A query using JSON_EXISTS(metadata, '$.tags[*]?(@ == "urgent")') to find all tickets tagged 'urgent' in their metadata JSON
2. A query using JSON_VALUE(metadata, '$.attachment_count' RETURNING NUMBER) to find all tickets with attachment_count > 0
3. A query that combines both: tickets that are either high-priority OR have the 'urgent' tag in metadata, using JSON_EXISTS combined with a regular WHERE condition on the priority column
4. A query demonstrating JSON_TABLE to unnest/flatten the tags array from metadata into individual rows (one row per ticket-tag pair), useful for a "tag frequency" report

Add comments explaining Oracle's native JSON data type support (23ai) versus older CLOB-based JSON handling, since this maps directly to the Unit 5 syllabus point.
```

**Testing prompt:**
```
Write tests/test_json_queries.py that:
1. Inserts 3 new temporary test tickets with controlled metadata JSON: one with tags containing "urgent", one with attachment_count=2, one with neither
2. Runs each of the 4 JSON queries and asserts exactly the expected temporary tickets show up in each result set (and no others, by filtering results to just the 3 test ticket_ids for clean assertions)
3. Asserts the JSON_TABLE tag-unnesting query produces one row per tag (e.g. if a ticket has tags ["billing","urgent"], confirm it appears as 2 separate rows in that specific query's output)
4. Cleans up the 3 temporary tickets in a finally block
```

---

## 18. Materialized view — daily summary

**Prompt:**
```
Write db/13_materialized_view.sql creating a materialized view daily_ticket_summary that:
- Groups by TRUNC(created_date) AS ticket_date
- Shows: total_tickets, open_count (COUNT WHERE status='OPEN'), resolved_count (COUNT WHERE status IN ('RESOLVED','CLOSED')), avg_resolution_days (AVG of resolved_date - created_date for resolved tickets that day)
- Uses BUILD IMMEDIATE and REFRESH COMPLETE ON DEMAND (explain in a comment why ON DEMAND rather than ON COMMIT is more appropriate here — avoiding refresh overhead on every single ticket insert)
- Include the exact DBMS_MVIEW.REFRESH('DAILY_TICKET_SUMMARY') PL/SQL call as a separate documented command (in a comment or a companion .sql snippet) for manually triggering refresh
```

**Testing prompt:**
```
Write tests/test_materialized_view.py that:
1. Queries daily_ticket_summary and records the current total_tickets sum across all rows
2. Inserts one new test ticket with today's date
3. Re-queries daily_ticket_summary WITHOUT refreshing and asserts the sum is UNCHANGED (proving it's a snapshot, not live)
4. Executes DBMS_MVIEW.REFRESH('DAILY_TICKET_SUMMARY') via oracledb (using a PL/SQL block executed through the connection)
5. Re-queries daily_ticket_summary again and asserts the sum now INCLUDES the new test ticket
6. Cleans up the test ticket and refreshes once more to restore the original state, in a finally block
Print each step's total_tickets value so I can see the before/no-refresh/after-refresh progression clearly for a report screenshot.
```

---

## 19. Time zone handling

**Prompt:**
```
Write db/14_timezone_support.sql that:
1. Alters the Tickets table to add a new column created_date_tz TIMESTAMP WITH TIME ZONE
2. Writes a one-time backfill UPDATE statement that populates created_date_tz from the existing created_date, assuming existing data is in IST ('Asia/Kolkata') — cast appropriately using AT TIME ZONE or FROM_TZ
3. Writes a query that inserts 3 new demo tickets with the SAME wall-clock time (e.g. '2026-08-11 14:00:00') but explicitly tagged with 3 different time zones: 'Asia/Kolkata' (IST), 'America/New_York' (EST/EDT), 'Europe/London' (GMT/BST) — using FROM_TZ(TIMESTAMP '...', 'zone_name')
4. Writes a reporting query that converts all created_date_tz values to a single unified UTC view for cross-region comparison, using created_date_tz AT TIME ZONE 'UTC', ordering results and clearly labeling both the original zone and the converted UTC time
```

**Testing prompt:**
```
Write tests/test_timezone.py that:
1. Runs the 3-region insert from the prompt above
2. Runs the UTC conversion query and asserts the 3 tickets, despite having identical wall-clock times, show DIFFERENT UTC timestamps (specifically: IST should be UTC-5:30 behind its wall clock, EST should be UTC-5 or -4 behind depending on DST, GMT/BST should be UTC+0 or +1 depending on DST) — assert the actual time differences numerically rather than just checking they're different
3. Prints a clear table: region | wall_clock_time | utc_converted_time | offset_hours, for direct inclusion in the report's globalization-support section
```

---

## 20. Streamlit frontend

**Prompt:**
```
Write app/streamlit_app.py with:
1. Page config: title "Multilingual Support Ticket Assistant", wide layout
2. A sidebar showing basic stats pulled live from the DB: total tickets, count by status (OPEN/RESOLVED/CLOSED), count by language — using a cached DB query function (st.cache_data with a short TTL like 30s) so the sidebar doesn't hammer the DB on every rerun
3. Main area: a text_area for entering a new ticket description, a selectbox for optional language hint (Auto-detect / English / Hindi / Tamil — note: auto-detect can just be a label, actual detection isn't required, the multilingual model handles it regardless), and a "Find Similar Tickets" button
4. On button click: show a spinner, call embeddings/generate.py to embed the input text, call embeddings/similarity_search.py's find_similar_tickets(), and display each of the top-3 results as a styled st.container or st.expander card showing: similarity score as a percentage/progress bar, original description, language badge, category, and the suggested resolution text prominently highlighted
5. Handle the edge case of empty input (show a warning, don't call the DB) and the edge case of zero results (e.g. if all resolved tickets happen to be excluded somehow — show a friendly "no similar tickets found" message)
6. Add basic error handling around the DB connection so if Oracle is down, the app shows a clear error message instead of crashing
7. Cache the sentence-transformer model load using st.cache_resource so it's not reloaded on every interaction (this matters — model loading is slow)
```

**Testing prompt:**
```
Run `streamlit run app/streamlit_app.py` and manually walk through this test checklist, reporting the result of each:
1. On load, confirm the sidebar stats match the actual DB counts (cross-check against a direct SQL COUNT query)
2. Type in a Hindi ticket description that closely matches one of the seeded English tickets in meaning, click Find Similar Tickets, and confirm the matching English (and/or Tamil) ticket appears in the top-3 with a visibly high similarity score
3. Submit an empty description and confirm the warning message appears without any DB call happening (check by watching for the spinner — it should NOT appear)
4. Type a completely unrelated sentence (e.g. about weather) and confirm the returned "top-3" still return something but with visibly LOW similarity scores (proving the UI honestly reflects low-confidence matches rather than hiding them)
5. Stop the Docker container mid-session, submit a new query, and confirm the app shows a graceful error message rather than an unhandled traceback
Document each result with a screenshot for the final report/PPT.
```
