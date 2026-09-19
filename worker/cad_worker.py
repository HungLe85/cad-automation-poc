import os
import json
import csv
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

    messages = queue_client.peek_messages(max_messages=1)

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

    if not found:
        print("Queue is empty.")


if __name__ == "__main__":
    main()