"""Run with FreeCADCmd.exe, not with the project's regular Python interpreter.

Usage: FreeCADCmd.exe worker/freecad_generator.py output/JOB-000009/job.json
"""
import json
import os
import re
import sys

import FreeCAD as App
import Part


def main():
    job_json_path = os.environ.get("CAD_JOB_JSON")

    if not job_json_path:
        raise ValueError(
            "Missing CAD_JOB_JSON environment variable"
        )

    with open(job_json_path, "r", encoding="utf-8") as source:
        job = json.load(source)
    job_id = job["job_id"]
    if not re.fullmatch(r"JOB-\d{6,}", job_id):
        raise ValueError("Invalid job_id")

    width = float(job["width"])
    height = float(job["height"])
    depth = float(job["depth"])

    if not all(0 < dimension <= 10000 for dimension in (width, height, depth)):
        raise ValueError("Cabinet dimensions must be between 0 and 10000 mm")

    output_dir = os.path.abspath(
        os.path.join(os.getcwd(), "output", job_id)
    )
    os.makedirs(output_dir, exist_ok=True)

    doc = App.newDocument("Cabinet3D")
    try:
        thickness = 2.0

        if (
            width <= 2 * thickness
            or height <= 2 * thickness
            or depth <= thickness
        ):
            raise ValueError(
                "Cabinet dimensions are too small for 2 mm walls"
            )

        outer_box = Part.makeBox(
            width,
            depth,
            height
        )

        # Inner cavity
        # Extend the cavity beyond the front face
        # so the cabinet remains open at the front.
        inner_box = Part.makeBox(
            width - 2 * thickness,
            depth,
            height - 2 * thickness,
            App.Vector(
                thickness,
                -thickness,
                thickness
            )
        )

        # Subtract inner cavity from outer cabinet
        cabinet = outer_box.cut(inner_box)

        # Remove unnecessary splitter edges
        cabinet = cabinet.removeSplitter()

        # Add cabinet body to FreeCAD document
        obj = doc.addObject(
            "PartDesign::Feature",
            "CabinetBody"
        )

        obj.Shape = cabinet
        obj.Label = "Cabinet Body"

        doc.recompute()
        if obj.Shape.isNull() or not obj.Shape.isValid():
            raise RuntimeError("FreeCAD produced an invalid shape")

        fcstd_path = os.path.join(output_dir, "Cabinet_3D.FCStd")
        step_path = os.path.join(output_dir, "Cabinet_3D.step")
        doc.saveAs(fcstd_path)
        Part.export([obj], step_path)

        for path in (fcstd_path, step_path):
            if not os.path.isfile(path) or os.path.getsize(path) == 0:
                raise RuntimeError("Missing or empty CAD output: " + path)

        print("3D model created successfully!")
        print(fcstd_path)
        print(step_path)
    finally:
        App.closeDocument(doc.Name)


main()