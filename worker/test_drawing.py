
from drawing_generator import generate_drawing

job = {
    "job_id": "JOB-TEST-001",
    "customer_name": "Hung POC",
    "width": 900,
    "height": 1900,
    "depth": 700,
    "material": "Stainless Steel",
    "door_type": "Double",
    "shelf_count": 6,
    "quantity": 2,
}

pdf_file = generate_drawing(
    job,
    "output/JOB-TEST-001"
)

print("Drawing created successfully!")
print(pdf_file)