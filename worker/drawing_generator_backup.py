
from pathlib import Path

from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4


def generate_drawing(job, output_dir):
    """
    Generate a conceptual cabinet drawing PDF.
    Dimensions are in millimeters.
    """

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    pdf_file = output_dir / "Cabinet_Drawing.pdf"

    page_width, page_height = A4
    pdf = canvas.Canvas(str(pdf_file), pagesize=A4)

    width = int(job["width"])
    height = int(job["height"])
    depth = int(job["depth"])
    shelves = int(job["shelf_count"])
    quantity = int(job["quantity"])

    material = job["material"]
    door_type = job["door_type"]
    job_id = job["job_id"]

    # Title
    pdf.setFont("Helvetica-Bold", 18)
    pdf.drawString(45, page_height - 50, "CABINET DRAWING")

    pdf.setFont("Helvetica", 10)
    pdf.drawString(45, page_height - 70, f"Job ID: {job_id}")
    pdf.drawString(45, page_height - 85, "Conceptual drawing - not for manufacturing")

    # Drawing area
    max_drawing_width = 350
    max_drawing_height = 420

    scale = min(
        max_drawing_width / width,
        max_drawing_height / height
    )

    drawing_width = width * scale
    drawing_height = height * scale

    x = (page_width - drawing_width) / 2
    y = 230

    # Cabinet outline
    pdf.setLineWidth(2)
    pdf.rect(
        x,
        y,
        drawing_width,
        drawing_height
    )

    # Door division
    if door_type == "Double":
        pdf.setLineWidth(1)
        pdf.line(
            x + drawing_width / 2,
            y,
            x + drawing_width / 2,
            y + drawing_height
        )

    # Shelves
    pdf.setLineWidth(0.7)

    for i in range(1, shelves + 1):
        shelf_y = y + drawing_height * i / (shelves + 1)

        pdf.line(
            x + 5,
            shelf_y,
            x + drawing_width - 5,
            shelf_y
        )

    # Width dimension
    pdf.setFont("Helvetica", 10)
    pdf.drawCentredString(
        x + drawing_width / 2,
        y - 20,
        f"WIDTH: {width} mm"
    )

    # Height dimension
    pdf.drawString(
        x + drawing_width + 10,
        y + drawing_height / 2,
        f"H: {height} mm"
    )

    # Configuration
    pdf.setFont("Helvetica-Bold", 12)
    pdf.drawString(45, 180, "CABINET CONFIGURATION")

    pdf.setFont("Helvetica", 10)

    details = [
        f"Width: {width} mm",
        f"Height: {height} mm",
        f"Depth: {depth} mm",
        f"Material: {material}",
        f"Door type: {door_type}",
        f"Shelves: {shelves}",
        f"Quantity: {quantity}",
    ]

    detail_y = 160

    for detail in details:
        pdf.drawString(45, detail_y, detail)
        detail_y -= 15

    pdf.save()

    return pdf_file