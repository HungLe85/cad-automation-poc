"""Generate a configurable cabinet with doors and shelves using FreeCADCmd.exe.

Run from the project root with CAD_JOB_JSON set to an absolute job.json path.
Outputs: output/JOB-xxxxxx/Cabinet_3D.FCStd and Cabinet_3D.step.
"""
import json
import os
import re

import FreeCAD as App
import Part


def add_part(doc, name, label, shape):
    if shape.isNull() or not shape.isValid():
        raise RuntimeError("Invalid FreeCAD shape: " + label)
    obj = doc.addObject("PartDesign::Feature", name)
    obj.Shape = shape
    obj.Label = label
    return obj


def main():
    job_json_path = os.environ.get("CAD_JOB_JSON")
    if not job_json_path:
        raise ValueError("Missing CAD_JOB_JSON environment variable")

    with open(job_json_path, "r", encoding="utf-8") as source:
        job = json.load(source)

    job_id = str(job["job_id"])
    if not re.fullmatch(r"JOB-\d{6,}", job_id):
        raise ValueError("Invalid job_id")

    width = float(job["width"])
    height = float(job["height"])
    depth = float(job["depth"])
    door_type = str(job.get("door_type", "Single")).strip().lower()
    shelf_count = int(job.get("shelf_count", 0))

    if not all(0 < dimension <= 10000 for dimension in (width, height, depth)):
        raise ValueError("Cabinet dimensions must be between 0 and 10000 mm")
    if door_type not in ("single", "double"):
        raise ValueError("door_type must be Single or Double")
    if not 0 <= shelf_count <= 30:
        raise ValueError("shelf_count must be between 0 and 30")

    wall = 2.0
    door_gap = 3.0
    if width <= 4 * wall + 3 * door_gap or height <= 4 * wall + 2 * door_gap or depth <= 3 * wall:
        raise ValueError("Cabinet dimensions are too small for walls, doors and shelves")
    if shelf_count and (height - 2 * wall) / (shelf_count + 1) <= wall:
        raise ValueError("Not enough vertical space for the requested shelves")

    output_dir = os.path.abspath(os.path.join(os.getcwd(), "output", job_id))
    os.makedirs(output_dir, exist_ok=True)
    doc = App.newDocument("Cabinet3D")
    try:
        # X = width, Y = depth (front at Y=0), Z = height.
        outer = Part.makeBox(width, depth, height)
        # Cavity passes through the front, leaving rear, side, top and bottom walls.
        cavity = Part.makeBox(
            width - 2 * wall,
            depth,
            height - 2 * wall,
            App.Vector(wall, -wall, wall),
        )
        body = outer.cut(cavity).removeSplitter()
        objects = [add_part(doc, "CabinetBody", "Cabinet Body (2 mm)", body)]

        # Separate solid shelf plates, evenly distributed vertically.
        shelf_width = width - 2 * wall
        shelf_depth = depth - 2 * wall
        for i in range(1, shelf_count + 1):
            shelf_z = wall + (height - 2 * wall) * i / (shelf_count + 1)
            shelf = Part.makeBox(
                shelf_width, shelf_depth, wall,
                App.Vector(wall, wall, shelf_z),
            )
            objects.append(add_part(doc, "Shelf%02d" % i, "Shelf %02d" % i, shelf))

        # Doors are shown OPEN (~105 degrees) so the shelves remain visible.
        # They are simple solid plates, not yet hinged or sheet-metal detailed.
        door_height = height - 2 * door_gap
        if door_type == "single":
            panel_width = width - 2 * door_gap
            door = Part.makeBox(
                panel_width, wall, door_height,
                App.Vector(door_gap, -wall, door_gap),
            )
            door.rotate(App.Vector(door_gap, 0, 0), App.Vector(0, 0, 1), -105)
            objects.append(add_part(doc, "DoorSingle", "Single Door (open)", door))
        else:
            panel_width = (width - 3 * door_gap) / 2
            left = Part.makeBox(
                panel_width, wall, door_height,
                App.Vector(door_gap, -wall, door_gap),
            )
            left.rotate(App.Vector(door_gap, 0, 0), App.Vector(0, 0, 1), -105)
            objects.append(add_part(doc, "DoorLeft", "Left Door (open)", left))

            right_start = width - door_gap - panel_width
            right = Part.makeBox(
                panel_width, wall, door_height,
                App.Vector(right_start, -wall, door_gap),
            )
            right.rotate(App.Vector(width - door_gap, 0, 0), App.Vector(0, 0, 1), 105)
            objects.append(add_part(doc, "DoorRight", "Right Door (open)", right))

        doc.recompute()
        fcstd_path = os.path.join(output_dir, "Cabinet_3D.FCStd")
        step_path = os.path.join(output_dir, "Cabinet_3D.step")
        doc.saveAs(fcstd_path)
        Part.export(objects, step_path)

        for path in (fcstd_path, step_path):
            if not os.path.isfile(path) or os.path.getsize(path) == 0:
                raise RuntimeError("Missing or empty CAD output: " + path)

        print("3D model created successfully!")
        print("Door type: %s; shelves: %d" % (door_type, shelf_count))
        print(fcstd_path)
        print(step_path)
    finally:
        App.closeDocument(doc.Name)


if __name__ == "__main__":
    main()
