# Cloud CAD Automation POC

A portfolio POC combining Codex-assisted development, Railway, Microsoft Azure,
DriveWorks, and SOLIDWORKS.

## Current milestone

Milestone 1 implements:

- Product configuration web form
- REST API
- Job persistence
- Docker deployment
- PostgreSQL-ready configuration for Railway

The app falls back to local SQLite when `DATABASE_URL` is empty.

## Run locally

### Python

```bash
python -m venv .venv
```

Windows:

```powershell
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Open:

```text
http://127.0.0.1:8000
```

### Docker

```bash
docker build -t cad-poc .
docker run --rm -p 8000:8000 cad-poc
```

## Railway deployment

1. Push this folder to a GitHub repository.
2. In Railway, create a project and deploy the GitHub repo.
3. Add a PostgreSQL database to the same Railway project.
4. In the web service Variables tab, create/reference `DATABASE_URL` from the Postgres service.
5. Deploy the staged changes.
6. In the web service Networking settings, generate a public domain.
7. Test `/health` and create a CAD job from `/`.

Railway automatically detects the root `Dockerfile`.

## API

- `GET /health`
- `GET /api/jobs`
- `GET /api/jobs/{id}`
- `POST /jobs` (HTML form)

## Next milestone

Add:

- Azure Storage Queue
- Azure Blob Storage
- Local Windows mock CAD worker
- Job states: QUEUED -> PROCESSING -> COMPLETED / FAILED
- Generated mock PDF/BOM files

Then replace the mock generator with DriveWorks + SOLIDWORKS automation.
