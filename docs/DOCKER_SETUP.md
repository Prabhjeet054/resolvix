# Oracle Database 23ai Free (Docker)

This project expects Oracle Database 23ai Free on `localhost:1521/FREEPDB1`, started via `docker-compose.yml`.

## 1. Minimum system requirements

Oracle 23ai Free itself is capped at **2 GB RAM** and **2 CPU threads** inside the database, with **up to 12 GB** of user data. The *host* needs more headroom than that:

| Resource | Minimum | Recommended |
| --- | --- | --- |
| RAM for Docker / the VM | **4 GB** allocated to Docker Desktop, Colima, or Podman | **8 GB** |
| Disk | **~12–20 GB** free (image + `oracle_data` volume) | **20+ GB** |
| CPU | 2 cores | 4 cores |

On macOS, Docker Desktop / Colima / Podman often default to **2 GB** for the Linux VM. Raise that to at least **4 GB** before the first start, or the instance can crash during bootstrap.

Set `ORACLE_PWD` in `.env` (copy from `.env.example`). The container uses that value for `SYS` / `SYSTEM`. Match `ORACLE_PASSWORD` to the same value so the Python app can connect.

## 2. Pull, start, logs, and stop

From the project root (after `cp .env.example .env` and filling in passwords):

```bash
# Optional: accept the OCR license, then log in
docker login container-registry.oracle.com

# Pull the 23ai Free image
docker compose pull

# Start in the background
docker compose up -d

# Follow logs until the database is ready
docker compose logs -f ticket-oracle-db
# equivalent: docker logs -f ticket-oracle-db

# Health / status
docker compose ps
docker inspect --format='{{.State.Health.Status}}' ticket-oracle-db

# Stop (keeps the oracle_data volume)
docker compose stop

# Stop and remove the container (volume is kept unless you pass -v)
docker compose down
```

## 3. First startup time and “ready” log line

The **first** start creates the database files in the `oracle_data` volume. That commonly takes **10–20 minutes** on the full `free:latest` image (sometimes longer on a cold pull). Later starts are usually **1–3 minutes**.

Watch container logs for this banner:

```
#########################
DATABASE IS READY TO USE!
#########################
```

Until that line appears, the listener and `FREEPDB1` are not ready. The Compose healthcheck greps the same text from `/opt/oracle/diag/rdbms/free/FREE/trace/alert_FREE.log`.

Connect with DSN `localhost:1521/FREEPDB1` (service name `FREEPDB1`, not SID `FREE`, for application users).

## 4. Troubleshooting

### Port already in use (`1521` or `5500`)

Another Oracle, Docker, or local listener is bound to the port:

```bash
# macOS / Linux
lsof -i :1521
lsof -i :5500
```

Stop the other process, or change the *host* side of the mapping in `docker-compose.yml` (for example `"1522:1521"`) and update `ORACLE_DSN` accordingly. Port **5500** is EM Express; you can drop that mapping if you do not need it.

### Insufficient memory

Symptoms: container exits, `ORA-03113`, PMON/SMON crashes, or the alert log never reaches “DATABASE IS READY TO USE!”.

Give the container runtime at least **4 GB** (preferably **8 GB**):

```bash
# Docker Desktop: Settings → Resources → Memory
colima stop && colima start --memory 8 --cpu 4
podman machine set --memory 8192
```

Then `docker compose down` and `docker compose up -d` again. If the first bootstrap was interrupted, you may need `docker compose down -v` to recreate `oracle_data` (this **wipes** the database).

### Apple Silicon (ARM) architecture issues

Oracle publishes **native ARM64** 23ai Free images. Prefer those over x86 emulation:

- `container-registry.oracle.com/database/free:latest` often has a matching platform; confirm with `docker image inspect` (`Architecture: arm64`).
- If pull or start fails with `no matching manifest` or very slow Rosetta/QEMU emulation, pin an ARM tag such as `.../database/free:latest-lite` or an explicit `*-arm64` tag from Oracle’s registry.
- If you only have an **amd64** image, enable Rosetta (Docker Desktop → General → “Use Rosetta for x86/amd64”) **and** allocate extra RAM; emulation is slower and more likely to fail under 4 GB.
- Fallback image `gvenzl/oracle-free:latest` also ships multi-arch tags and does not require Oracle Container Registry login. Connection details still use `FREEPDB1` / `ORACLE_PWD`.

If the container stays “healthy” locally but clients cannot connect, confirm the listener is up (`docker exec ticket-oracle-db lsnrctl status`) and that you are using service `FREEPDB1` on the mapped host port.
