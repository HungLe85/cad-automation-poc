from io import BytesIO
from urllib.parse import urlparse, unquote

from azure.storage.blob import BlobServiceClient
from fastapi.responses import StreamingResponse
import os
import secrets

from fastapi import Header, HTTPException
from pydantic import BaseModel
from app.azure_queue import send_job_to_queue
from pathlib import Path
from fastapi import FastAPI, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from .db import Base, engine, SessionLocal
from .models import Job

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Cloud CAD Automation POC", version="0.1.0")
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@app.get("/health")
def health():
    return {"status": "ok", "service": "cad-automation-poc"}

@app.get("/", response_class=HTMLResponse)
def home(request: Request, db: Session = Depends(get_db)):
    jobs = db.query(Job).order_by(Job.id.desc()).limit(20).all()
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={"jobs": jobs},
    )

@app.post("/jobs")
def create_job(
    customer_name: str = Form("POC User"),
    width: int = Form(...),
    height: int = Form(...),
    depth: int = Form(...),
    material: str = Form(...),
    door_type: str = Form(...),
    shelf_count: int = Form(...),
    quantity: int = Form(...),
    db: Session = Depends(get_db),
):
    job = Job(
        customer_name=customer_name,
        width=width,
        height=height,
        depth=depth,
        material=material,
        door_type=door_type,
        shelf_count=shelf_count,
        quantity=quantity,
        status="QUEUED",
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    db.add(job)
    db.commit()
    db.refresh(job)

    job_data = {
        "job_id": f"JOB-{job.id:06d}",
        "customer_name": job.customer_name,
        "width": job.width,
        "height": job.height,
        "depth": job.depth,
        "material": job.material,
        "door_type": job.door_type,
        "shelf_count": job.shelf_count,
        "quantity": job.quantity,
        "status": job.status,
    }

    send_job_to_queue(job_data)

    return RedirectResponse(url="/", status_code=303)
    return RedirectResponse(url="/", status_code=303)

@app.get("/api/jobs")
def list_jobs(db: Session = Depends(get_db)):
    jobs = db.query(Job).order_by(Job.id.desc()).limit(100).all()
    return [
        {
            "id": j.id,
            "customer_name": j.customer_name,
            "width": j.width,
            "height": j.height,
            "depth": j.depth,
            "material": j.material,
            "door_type": j.door_type,
            "shelf_count": j.shelf_count,
            "quantity": j.quantity,
            "status": j.status,
            "output_url": j.output_url,
            "created_at": j.created_at.isoformat(),
        }
        for j in jobs
    ]

@app.get("/api/jobs/{job_id}")
def get_job(job_id: int, db: Session = Depends(get_db)):
    j = db.get(Job, job_id)
    if not j:
        return {"error": "job not found"}
    return {
        "id": j.id,
        "customer_name": j.customer_name,
        "configuration": {
            "width": j.width,
            "height": j.height,
            "depth": j.depth,
            "material": j.material,
            "door_type": j.door_type,
            "shelf_count": j.shelf_count,
            "quantity": j.quantity,
        },
        "status": j.status,
        "output_url": j.output_url,
        "created_at": j.created_at.isoformat(),
    }
class JobCompleteRequest(BaseModel):
    output_url: str


@app.patch("/api/jobs/{job_id}/complete")
def complete_job(
    job_id: int,
    payload: JobCompleteRequest,
    x_worker_api_key: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    expected_key = os.getenv("WORKER_API_KEY")

    if not expected_key:
        raise HTTPException(
            status_code=503,
            detail="Worker API key is not configured"
        )

    if not x_worker_api_key or not secrets.compare_digest(
        x_worker_api_key,
        expected_key
    ):
        raise HTTPException(
            status_code=401,
            detail="Unauthorized worker"
        )

    job = db.query(Job).filter(
        Job.id == job_id
    ).first()

    if not job:
        raise HTTPException(
            status_code=404,
            detail="Job not found"
        )

    job.status = "COMPLETED"
    job.output_url = payload.output_url

    db.commit()
    db.refresh(job)

    return {
        "id": job.id,
        "status": job.status,
        "output_url": job.output_url
    }
@app.get("/api/jobs/{job_id}/download")
def download_job_output(
    job_id: int,
    db: Session = Depends(get_db),
):
    job = db.query(Job).filter(Job.id == job_id).first()

    if not job:
        raise HTTPException(
            status_code=404,
            detail="Job not found"
        )

    if job.status != "COMPLETED" or not job.output_url:
        raise HTTPException(
            status_code=409,
            detail="Job output is not ready"
        )

    connection_string = os.getenv(
        "AZURE_STORAGE_CONNECTION_STRING"
    )

    if not connection_string:
        raise HTTPException(
            status_code=503,
            detail="Azure Storage is not configured"
        )

    try:
        blob_service = BlobServiceClient.from_connection_string(
            connection_string
        )

        parsed_url = urlparse(job.output_url)
        expected_host = (
            f"{blob_service.account_name}.blob.core.windows.net"
        )

        if parsed_url.hostname != expected_host:
            raise ValueError("Unexpected Blob Storage host")

        blob_path = unquote(parsed_url.path).lstrip("/")
        container_name, blob_name = blob_path.split("/", 1)

        if container_name != "cad-output":
            raise ValueError("Unexpected container")

        blob_client = blob_service.get_blob_client(
            container=container_name,
            blob=blob_name
        )

        file_data = blob_client.download_blob().readall()

        return StreamingResponse(
            BytesIO(file_data),
            media_type="text/csv",
            headers={
                "Content-Disposition": (
                    f'attachment; filename="JOB-{job_id:06d}-BOM.csv"'
                )
            }
        )

    except Exception:
        raise HTTPException(
            status_code=502,
            detail="Unable to download job output"
        )
@app.get("/api/jobs/{job_id}/drawing")
def download_job_drawing(
    job_id: int,
    db: Session = Depends(get_db),
):
    job = db.query(Job).filter(Job.id == job_id).first()

    if not job:
        raise HTTPException(
            status_code=404,
            detail="Job not found"
        )

    if job.status != "COMPLETED" or not job.output_url:
        raise HTTPException(
            status_code=409,
            detail="Job output is not ready"
        )

    connection_string = os.getenv(
        "AZURE_STORAGE_CONNECTION_STRING"
    )

    if not connection_string:
        raise HTTPException(
            status_code=503,
            detail="Azure Storage is not configured"
        )

    try:
        blob_service = BlobServiceClient.from_connection_string(
            connection_string
        )

        blob_name = (
            f"JOB-{job_id:06d}/Cabinet_Drawing.pdf"
        )

        blob_client = blob_service.get_blob_client(
            container="cad-output",
            blob=blob_name
        )

        file_data = blob_client.download_blob().readall()

        return StreamingResponse(
            BytesIO(file_data),
            media_type="application/pdf",
            headers={
                "Content-Disposition": (
                    f'attachment; filename="JOB-{job_id:06d}-Drawing.pdf"'
                )
            }
        )

    except Exception:
        raise HTTPException(
            status_code=502,
            detail="Unable to download drawing PDF"
        )


@app.get("/api/jobs/{job_id}/3d/{file_type}")
def download_job_3d(
    job_id: int,
    file_type: str,
    db: Session = Depends(get_db),
):
    file_options = {
        "freecad": (
            "Cabinet_3D.FCStd",
            "application/octet-stream",
        ),
        "step": (
            "Cabinet_3D.step",
            "application/step",
        ),
    }

    if file_type not in file_options:
        raise HTTPException(
            status_code=404,
            detail="Unsupported 3D file type",
        )

    job = db.query(Job).filter(Job.id == job_id).first()

    if not job:
        raise HTTPException(
            status_code=404,
            detail="Job not found",
        )

    if job.status != "COMPLETED" or not job.output_url:
        raise HTTPException(
            status_code=409,
            detail="Job output is not ready",
        )

    connection_string = os.getenv(
        "AZURE_STORAGE_CONNECTION_STRING"
    )

    if not connection_string:
        raise HTTPException(
            status_code=503,
            detail="Azure Storage is not configured",
        )

    filename, media_type = file_options[file_type]

    blob_name = f"JOB-{job_id:06d}/{filename}"

    try:
        blob_service = BlobServiceClient.from_connection_string(
            connection_string
        )

        blob_client = blob_service.get_blob_client(
            container="cad-output",
            blob=blob_name,
        )

        file_data = blob_client.download_blob().readall()

    except Exception:
        raise HTTPException(
            status_code=502,
            detail="Unable to download 3D file",
        )

    return StreamingResponse(
        BytesIO(file_data),
        media_type=media_type,
        headers={
            "Content-Disposition": (
                f'attachment; filename="JOB-{job_id:06d}-{filename}"'
            )
        },
    )
