from drawing_generator import generate_drawing
import time
import requests
import os
import json
import csv
import subprocess
from pathlib import Path

from azure.storage.queue import QueueClient
from azure.storage.blob import BlobServiceClient

def main():
    connection_string = os.getenv(
        "AZURE_STORAGE_CONNECTION_STRING"
    )

    queue_name = os.getenv(
        "AZURE_QUEUE_NAME",
        "cad-jobs"
    )

    if not connection_string:
        print("ERROR: Azure connection string not configured.")
        return

    queue_client = QueueClient.from_connection_string(
        conn_str=connection_string,
        queue_name=queue_name
    )

    print("Connected to Azure Queue:", queue_name)

    messages = queue_client.receive_messages(
    messages_per_page=1,
    visibility_timeout=300
)

    found = False

    for message in messages:
        found = True

        print("\nCAD JOB RECEIVED:")

        job = json.loads(message.content)

        print(json.dumps(job, indent=4))

        job_id = job["job_id"]

        output_dir = Path("output") / job_id

        output_dir.mkdir(
            parents=True,
            exist_ok=True
        )

        bom_file = output_dir / "BOM.csv"

        with open(
            bom_file,
            "w",
            newline="",
            encoding="utf-8-sig"
        ) as f:

            writer = csv.writer(f)

            writer.writerow([
                "Item",
                "Description",
                "Material",
                "Quantity"
            ])

            writer.writerow([
                1,
                "Cabinet Body",
                job["material"],
                job["quantity"]
            ])

            writer.writerow([
                2,
                "Cabinet Door",
                job["material"],
                job["quantity"] * (
                    2 if job["door_type"] == "Double" else 1
                )
            ])

            writer.writerow([
                3,
                "Shelf",
                job["material"],
                job["shelf_count"] * job["quantity"]
            ])

        print(f"\nBOM created: {bom_file}")

        drawing_file = generate_drawing(
            job,
            output_dir
        )

        print(f"Drawing created: {drawing_file}")

        # FreeCAD runs in its own Python environment via FreeCADCmd.exe.
        # Set FREECAD_CMD in your local .env, never commit the .env file.
        freecad_cmd = os.getenv(
            "FREECAD_CMD",
            r"C:\Program Files\FreeCAD 1.1\bin\FreeCADCmd.exe"
        )
        if not Path(freecad_cmd).is_file():
            raise FileNotFoundError(f"FreeCADCmd.exe not found: {freecad_cmd}")

        job_json = output_dir / "job.json"
        job_json.write_text(json.dumps(job, ensure_ascii=False), encoding="utf-8")
        generator_script = Path(__file__).resolve().parent / "freecad_generator.py"
        result = subprocess.run(
            [freecad_cmd, str(generator_script), str(job_json.resolve())],
            cwd=Path(__file__).resolve().parent.parent,
            capture_output=True,
            text=True,
            timeout=240,
            check=False,
        )
        if result.stdout:
            print(result.stdout)
        if result.stderr:
            print(result.stderr)
        if result.returncode != 0:
            raise RuntimeError(f"FreeCADCmd failed (exit code {result.returncode})")

        cad_files = [output_dir / "Cabinet_3D.FCStd", output_dir / "Cabinet_3D.step"]
        for cad_file in cad_files:
            if not cad_file.is_file() or cad_file.stat().st_size == 0:
                raise RuntimeError(f"CAD output missing or empty: {cad_file}")

        blob_service = BlobServiceClient.from_connection_string(
            connection_string
        )

        container_name = "cad-output"

        blob_name = f"{job_id}/BOM.csv"

        blob_client = blob_service.get_blob_client(
            container=container_name,
            blob=blob_name
        )

        with open(bom_file, "rb") as data:
            blob_client.upload_blob(
                data,
                overwrite=True
            )

        print("BOM uploaded to Azure Blob successfully!")
        print("Blob path:", blob_name)
        # Upload cabinet drawing PDF to Azure Blob
        drawing_blob_name = f"{job_id}/Cabinet_Drawing.pdf"

        drawing_blob_client = blob_service.get_blob_client(
            container=container_name,
            blob=drawing_blob_name
        )

        with open(drawing_file, "rb") as data:
            drawing_blob_client.upload_blob(
                data,
                overwrite=True,
                content_type="application/pdf"
            )

        print("Drawing uploaded to Azure Blob successfully!")
        print("Drawing Blob path:", drawing_blob_name)

        # Upload both CAD files before marking the job COMPLETED.
        for cad_file in cad_files:
            cad_blob_name = f"{job_id}/{cad_file.name}"
            cad_blob_client = blob_service.get_blob_client(
                container=container_name, blob=cad_blob_name
            )
            with cad_file.open("rb") as data:
                cad_blob_client.upload_blob(
                    data,
                    overwrite=True,
                    content_type=(
                        "application/step" if cad_file.suffix.lower() == ".step"
                        else "application/octet-stream"
                    ),
                )
            print("CAD uploaded to Azure Blob:", cad_blob_name)

        railway_api_url = os.getenv("RAILWAY_API_URL")
        worker_api_key = os.getenv("WORKER_API_KEY")

        if not railway_api_url or not worker_api_key:
            print("ERROR: Railway API configuration missing.")
            return

        job_number = int(job_id.split("-")[-1])

        completion_url = (
            f"{railway_api_url}/api/jobs/"
            f"{job_number}/complete"
        )

        response = requests.patch(
            completion_url,
            headers={
                "X-Worker-API-Key": worker_api_key
            },
            json={
                "output_url": blob_client.url
            },
            timeout=30
        )

        response.raise_for_status()

        print("\nRailway Job updated successfully!")
        print(json.dumps(response.json(), indent=4))
        queue_client.delete_message(message.id, message.pop_receipt)
        print(f"Azure Queue message deleted: {job_id}")

    if not found:
        print("Queue is empty.")


if __name__ == "__main__":
    print("CAD Worker started. Waiting for new jobs...")

    while True:
        try:
            main()
        except Exception as exc:
            print(f"Worker error: {exc}")

        time.sleep(10)