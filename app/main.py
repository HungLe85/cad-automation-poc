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
