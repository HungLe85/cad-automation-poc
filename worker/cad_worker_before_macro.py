"""Azure Queue CAD worker: BOM + PDF + FreeCAD FCStd/STEP.

Run with the project's .venv Python from the project root.
FreeCAD itself is invoked separately using FreeCADCmd.exe.
"""
from dotenv import load_dotenv

load_dotenv()
import csv
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

import requests
from azure.storage.blob import BlobServiceClient, ContentSettings
from azure.storage.queue import QueueClient
from drawing_generator import generate_drawing

PROJECT_DIR = Path(__file__).resolve().parent.parent
OUTPUT_ROOT = PROJECT_DIR / "output"
GENERATOR = PROJECT_DIR / "worker" / "freecad_generator.py"
DEFAULT_FREECAD_CMD = r"C:\Program Files\FreeCAD 1.1\bin\FreeCADCmd.exe"
CONTENT_TYPES = {
    "BOM.csv": "text/csv",
    "Cabinet_Drawing.pdf": "application/pdf",
    "Cabinet_3D.FCStd": "application/octet-stream",
    "Cabinet_3D.step": "application/step",
}


def create_cad_files(job, output_dir):
    job_file = output_dir / "job.json"
    job_file.write_text(json.dumps(job, ensure_ascii=False, indent=2), encoding="utf-8")

    freecad_cmd = Path(os.getenv("FREECAD_CMD", DEFAULT_FREECAD_CMD))
    if not freecad_cmd.is_file():
        raise FileNotFoundError(f"FreeCADCmd.exe not found: {freecad_cmd}")
    if not GENERATOR.is_file():
        raise FileNotFoundError(f"FreeCAD generator not found: {GENERATOR}")

    command = [str(freecad_cmd), str(GENERATOR)]

    env = os.environ.copy()
    env["CAD_JOB_JSON"] = str(job_file.resolve())

    print("Generating 3D model with FreeCAD...", flush=True)

    result = subprocess.run(
        command,
        cwd=str(PROJECT_DIR),
        env=env,
        capture_output=True,
        text=True,
        errors="replace",
        timeout=180,
        check=False,
    )
    if result.stdout:
        print(result.stdout, flush=True)
    if result.stderr:
        print(result.stderr, file=sys.stderr, flush=True)

    # Some FreeCADCmd builds do not propagate script errors as process exit codes.
    if result.returncode != 0 or "Traceback" in (result.stdout + result.stderr):
        raise RuntimeError(f"FreeCAD generation failed (exit code {result.returncode})")

    files = [output_dir / "Cabinet_3D.FCStd", output_dir / "Cabinet_3D.step"]
    for path in files:
        if not path.is_file() or path.stat().st_size == 0:
            raise RuntimeError(f"FreeCAD output missing or empty: {path}")
    return files


def process_message(message, queue_client, blob_service, railway_api_url, worker_api_key):
    job = json.loads(message.content)
    job_id = str(job["job_id"])
    if not re.fullmatch(r"JOB-\d{6,}", job_id):
        raise ValueError(f"Unexpected job ID: {job_id}")
    print(f"\nCAD JOB RECEIVED: {job_id}", flush=True)

    output_dir = OUTPUT_ROOT / job_id
    output_dir.mkdir(parents=True, exist_ok=True)

    bom_file = output_dir / "BOM.csv"
    quantity = int(job["quantity"])
    shelves = int(job["shelf_count"])
    with bom_file.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(["Item", "Description", "Material", "Quantity"])
        writer.writerow([1, "Cabinet Body", job["material"], quantity])
        writer.writerow([2, "Cabinet Door", job["material"], quantity * (2 if job["door_type"] == "Double" else 1)])
        writer.writerow([3, "Shelf", job["material"], shelves * quantity])
    print(f"BOM created: {bom_file}", flush=True)

    drawing_file = Path(generate_drawing(job, output_dir))
    print(f"Drawing created: {drawing_file}", flush=True)

    cad_files = create_cad_files(job, output_dir)
    files = [bom_file, drawing_file, *cad_files]
    uploaded = {}
    for path in files:
        if not path.is_file() or path.stat().st_size == 0:
            raise RuntimeError(f"Output missing or empty: {path}")
        blob = blob_service.get_blob_client(container="cad-output", blob=f"{job_id}/{path.name}")
        with path.open("rb") as data:
            blob.upload_blob(
                data,
                overwrite=True,
                content_settings=ContentSettings(content_type=CONTENT_TYPES[path.name]),
            )
        uploaded[path.name] = blob.url
        print(f"Uploaded to Azure Blob: {job_id}/{path.name}", flush=True)

    if not railway_api_url or not worker_api_key:
        raise RuntimeError("RAILWAY_API_URL or WORKER_API_KEY missing")
    job_number = int(job_id.rsplit("-", 1)[1])
    response = requests.patch(
        f"{railway_api_url.rstrip('/')}/api/jobs/{job_number}/complete",
        headers={"X-Worker-API-Key": worker_api_key},
        # Keep existing Railway API contract: one output_url (BOM URL).
        json={"output_url": uploaded["BOM.csv"]},
        timeout=30,
    )
    response.raise_for_status()
    print(f"Railway job completed: {job_id}", flush=True)
    queue_client.delete_message(message.id, message.pop_receipt)
    print(f"Azure Queue message deleted: {job_id}", flush=True)


def main():
    connection_string = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
    if not connection_string:
        raise RuntimeError("AZURE_STORAGE_CONNECTION_STRING not configured")
    queue_client = QueueClient.from_connection_string(
        conn_str=connection_string,
        queue_name=os.getenv("AZURE_QUEUE_NAME", "cad-jobs"),
    )
    blob_service = BlobServiceClient.from_connection_string(connection_string)
    railway_api_url = os.getenv("RAILWAY_API_URL")
    worker_api_key = os.getenv("WORKER_API_KEY")
    print("CAD Worker started. Waiting for new jobs...", flush=True)
    while True:
        try:
            messages = queue_client.receive_messages(messages_per_page=1, visibility_timeout=600)
            found = False
            for message in messages:
                found = True
                try:
                    process_message(message, queue_client, blob_service, railway_api_url, worker_api_key)
                except Exception as exc:
                    # Leave message in queue for retry after visibility timeout.
                    print(f"Worker error: {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
            if not found:
                print("Queue is empty.", flush=True)
        except Exception as exc:
            print(f"Queue error: {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
        time.sleep(10)


if __name__ == "__main__":
    main()
