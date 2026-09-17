import json
import os

from azure.storage.queue import QueueClient


def send_job_to_queue(job_data: dict) -> bool:
    connection_string = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
    queue_name = os.getenv("AZURE_QUEUE_NAME", "cad-jobs")

    if not connection_string:
        print("AZURE_STORAGE_CONNECTION_STRING is not configured.")
        return False

    try:
        queue_client = QueueClient.from_connection_string(
            conn_str=connection_string,
            queue_name=queue_name,
        )

        message = json.dumps(job_data)

        queue_client.send_message(message)

        print(
            f"Azure Queue: sent {job_data.get('job_id')} "
            f"to queue '{queue_name}'"
        )

        return True

    except Exception as exc:
        print(f"Azure Queue error: {exc}")
        return False