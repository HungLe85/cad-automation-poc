"""Conceptual cabinet drawing generator (PDF V2).

Drop-in replacement for worker/drawing_generator.py.
Uses the existing generate_drawing(job, output_dir) interface.
Not a manufacturing drawing or a SOLIDWORKS export.
"""
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.pdfgen import canvas


PT_PER_MM = 72 / 25.4


def _dimension_h(pdf, x1, x2, y, reference_y, label):
    pdf.setLineWidth(0.6)
    pdf.line(x1, reference_y, x1, y - 5)
    pdf.line(x2, reference_y, x2, y - 5)
    pdf.line(x1, y, x2, y)
    for x, direction in ((x1, 1), (x2, -1)):
        pdf.line(x, y, x + 6 * direction, y + 3)
        pdf.line(x, y, x + 6 * direction, y - 3)
    pdf.setFont("Helvetica", 8)
    pdf.drawCentredString((x1 + x2) / 2, y - 14, label)


def _dimension_v(pdf, x, y1, y2, reference_x, label):
    pdf.setLineWidth(0.6)
    pdf.line(reference_x, y1, x + 5, y1)
    pdf.line(reference_x, y2, x + 5, y2)
    pdf.line(x, y1, x, y2)
    for y, direction in ((y1, 1), (y2, -1)):
        pdf.line(x, y, x - 3, y + 6 * direction)
        pdf.line(x, y, x + 3, y + 6 * direction)
    pdf.saveState()
    pdf.translate(x - 12, (y1 + y2) / 2)
    pdf.rotate(90)
    pdf.setFont("Helvetica", 8)
    pdf.drawCentredString(0, 0, label)
    pdf.restoreState()


def _view_label(pdf, text, x, y, width):
    pdf.setFont("Helvetica-Bold", 9)
    pdf.drawCentredString(x + width / 2, y, text)


def _page_header(pdf, page_w, page_h, job_id, page_no):
    pdf.setFont("Helvetica-Bold", 17)
    pdf.drawString(38, page_h - 42, "CABINET DRAWING - CONCEPT V2")
    pdf.setFont("Helvetica", 9)
    pdf.drawString(38, page_h - 58, f"Job ID: {job_id} | Page {page_no} of 2")
    pdf.setFillColor(colors.darkred)
    pdf.drawRightString(page_w - 38, page_h - 58, "NOT FOR MANUFACTURING")
    pdf.setFillColor(colors.black)
    pdf.line(38, page_h - 68, page_w - 38, page_h - 68)


def generate_drawing(job, output_dir):
    """Create a two-page conceptual PDF and return its Path."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    pdf_file = output_dir / "Cabinet_Drawing.pdf"

    width = int(job["width"])
    height = int(job["height"])
    depth = int(job["depth"])
    shelves = int(job["shelf_count"])
    quantity = int(job["quantity"])
    material = str(job["material"])
    door_type = str(job["door_type"])
    job_id = str(job["job_id"])

    if min(width, height, depth, quantity) <= 0 or shelves < 0:
        raise ValueError("Dimensions and quantity must be positive; shelves cannot be negative")
    if door_type not in ("Single", "Double"):
        raise ValueError("door_type must be Single or Double")

    page_w, page_h = landscape(A4)
    pdf = canvas.Canvas(str(pdf_file), pagesize=(page_w, page_h))
    pdf.setTitle(f"{job_id} - Cabinet Drawing V2")

    # Page 1: three orthographic conceptual views.
    _page_header(pdf, page_w, page_h, job_id, 1)
    # Reserve separate vertical bands for front/side and top/configuration.
    # A shared scale keeps the three views proportionate.
    max_h = 235
    max_front_w = 230
    max_side_w = 125
    max_top_h = 92
    scale = min(max_h / height, max_front_w / width,
                max_side_w / depth, max_top_h / depth)
    fw, fh, sw = width * scale, height * scale, depth * scale
    x_front, y_base = 110, 238
    x_side = max(455, x_front + fw + 90)

    pdf.setLineWidth(1.4)
    pdf.rect(x_front, y_base, fw, fh)
    if door_type == "Double":
        pdf.setLineWidth(0.9)
        pdf.line(x_front + fw / 2, y_base, x_front + fw / 2, y_base + fh)
    else:
        pdf.setLineWidth(0.9)
        pdf.line(x_front + fw - 9, y_base + fh * 0.46,
                 x_front + fw - 9, y_base + fh * 0.54)

    pdf.setDash(3, 3)
    pdf.setLineWidth(0.6)
    for i in range(1, shelves + 1):
        sy = y_base + fh * i / (shelves + 1)
        pdf.line(x_front + 4, sy, x_front + fw - 4, sy)
    pdf.setDash()
    _view_label(pdf, "FRONT VIEW", x_front, y_base + fh + 14, fw)
    _dimension_h(pdf, x_front, x_front + fw, y_base - 19, y_base, f"W {width} mm")
    _dimension_v(pdf, x_front - 25, y_base, y_base + fh, x_front, f"H {height} mm")

    pdf.setLineWidth(1.4)
    pdf.rect(x_side, y_base, sw, fh)
    pdf.setDash(3, 3)
    pdf.setLineWidth(0.6)
    for i in range(1, shelves + 1):
        sy = y_base + fh * i / (shelves + 1)
        pdf.line(x_side + 4, sy, x_side + sw - 4, sy)
    pdf.setDash()
    _view_label(pdf, "SIDE VIEW", x_side, y_base + fh + 14, sw)
    _dimension_h(pdf, x_side, x_side + sw, y_base - 19, y_base, f"D {depth} mm")

    top_y = 72
    top_h = depth * scale
    pdf.setLineWidth(1.4)
    pdf.rect(x_front, top_y, fw, top_h)
    if door_type == "Double":
        pdf.setLineWidth(0.6)
        pdf.line(x_front + fw / 2, top_y, x_front + fw / 2, top_y + top_h)
    _view_label(pdf, "TOP VIEW", x_front, top_y + top_h + 12, fw)

    pdf.setFont("Helvetica-Bold", 10)
    pdf.drawString(455, 185, "CABINET CONFIGURATION")
    pdf.setFont("Helvetica", 9)
    details = [
        f"Width x Height x Depth: {width} x {height} x {depth} mm",
        f"Material: {material}",
        f"Door type: {door_type}",
        f"Shelves per cabinet: {shelves}",
        f"Cabinet quantity: {quantity}",
        "Dashed lines: conceptual shelf locations",
    ]
    for idx, detail in enumerate(details):
        pdf.drawString(455, 165 - idx * 14, detail)
    pdf.setFont("Helvetica-Oblique", 8)
    pdf.drawString(38, 24, "Conceptual only. No tolerances, sheet thickness, joinery or manufacturing details specified.")
    pdf.showPage()

    # Page 2: BOM aligned with existing worker's simple BOM quantities.
    _page_header(pdf, page_w, page_h, job_id, 2)
    pdf.setFont("Helvetica-Bold", 12)
    pdf.drawString(38, page_h - 100, "BILL OF MATERIALS - CONCEPTUAL")
    columns = [48, 105, 360, 590]
    headers = ["ITEM", "DESCRIPTION", "MATERIAL", "QUANTITY"]
    for x, label in zip(columns, headers):
        pdf.setFont("Helvetica-Bold", 10)
        pdf.drawString(x, page_h - 134, label)
    pdf.line(38, page_h - 142, page_w - 38, page_h - 142)
    rows = [
        ("1", "Cabinet Body", material, quantity),
        ("2", "Cabinet Door", material, quantity * (2 if door_type == "Double" else 1)),
        ("3", "Shelf", material, shelves * quantity),
    ]
    for idx, row in enumerate(rows):
        y = page_h - 165 - idx * 29
        pdf.setFont("Helvetica", 10)
        for x, value in zip(columns, row):
            pdf.drawString(x, y, str(value))
        pdf.setStrokeColor(colors.lightgrey)
        pdf.line(38, y - 8, page_w - 38, y - 8)
        pdf.setStrokeColor(colors.black)
    pdf.setFont("Helvetica", 9)
    pdf.drawString(38, page_h - 292, f"Cabinet size: {width} x {height} x {depth} mm")
    pdf.drawString(38, page_h - 310, f"Door: {door_type} | Shelves per cabinet: {shelves} | Quantity: {quantity}")
    pdf.setFont("Helvetica-Oblique", 9)
    pdf.drawString(38, 50, "BOM quantities are illustrative and do not include fasteners, hinges, finishes or material cut lists.")
    pdf.drawString(38, 34, "Drawing and BOM are not suitable for fabrication or procurement without engineering review.")
    pdf.save()
    return pdf_file
