"""Export build123d parts as multi-color 3MF files with alternating layer colors.

Each triangle in the tessellated mesh is assigned a material based on which
print layer its Z centroid falls in.  When opened in Bambu Studio the
per-triangle colours map to AMS filament slots, giving alternating layer
colours without manual painting.
"""

import argparse
import math

import lib3mf


def export_multicolor_3mf(
    part,
    filename: str,
    layer_height: float,
    colors: list[str] | None = None,
    tolerance: float = 0.01,
) -> None:
    """Export a build123d Part as a 3MF with alternating layer colours.

    Args:
        part: A build123d Part (or Shape with a tessellate method).
        filename: Output .3mf file path.
        layer_height: Print layer height in mm.
        colors: Hex colour strings (e.g. ["#FF0000", "#0000FF"]).
                Defaults to red and blue if not supplied.
        tolerance: Tessellation tolerance passed to Part.tessellate().
    """
    if colors is None:
        colors = ["#FF0000", "#0000FF"]
    if len(colors) < 2:
        raise ValueError("Need at least two colours for alternating layers")

    # Tessellate the part
    vertices, faces = part.tessellate(tolerance)

    # Build 3MF model
    wrapper = lib3mf.get_wrapper()
    model = wrapper.CreateModel()
    mesh = model.AddMeshObject()
    mesh.SetName("part")

    # Add vertices
    vert_buf = []
    for v in vertices:
        pos = lib3mf.Position()
        pos.Coordinates[0] = float(v.X)
        pos.Coordinates[1] = float(v.Y)
        pos.Coordinates[2] = float(v.Z)
        vert_buf.append(pos)
    mesh.SetGeometry(vert_buf, [])  # set vertices first, triangles below

    # Create material group with colours
    mat_group = model.AddBaseMaterialGroup()
    mat_indices = []
    for i, hex_color in enumerate(colors):
        r, g, b = _hex_to_rgb(hex_color)
        color = wrapper.RGBAToColor(r, g, b, 255)
        mat_indices.append(mat_group.AddMaterial(f"Color{i}", color))
    mat_id = mat_group.GetResourceID()

    # Add triangles with per-triangle material assignment
    tri_buf = []
    for f in faces:
        tri = lib3mf.Triangle()
        tri.Indices[0] = f[0]
        tri.Indices[1] = f[1]
        tri.Indices[2] = f[2]
        tri_buf.append(tri)

    mesh.SetGeometry(vert_buf, tri_buf)

    # Assign material to each triangle based on Z centroid
    for i, f in enumerate(faces):
        z_centroid = (
            float(vertices[f[0]].Z)
            + float(vertices[f[1]].Z)
            + float(vertices[f[2]].Z)
        ) / 3.0
        layer_index = int(z_centroid / layer_height)
        prop_id = mat_indices[layer_index % len(colors)]

        props = lib3mf.TriangleProperties()
        props.ResourceID = mat_id
        props.PropertyIDs[0] = prop_id
        props.PropertyIDs[1] = prop_id
        props.PropertyIDs[2] = prop_id
        mesh.SetTriangleProperties(i, props)

    # Set default property so the object is recognised as multi-material
    mesh.SetObjectLevelProperty(mat_id, mat_indices[0])

    # Add to build
    model.AddBuildItem(mesh, wrapper.GetIdentityTransform())

    # Write file
    writer = model.QueryWriter("3mf")
    writer.WriteToFile(filename)


def _hex_to_rgb(hex_str: str) -> tuple[int, int, int]:
    """Convert '#RRGGBB' to (R, G, B) ints."""
    h = hex_str.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def main():
    parser = argparse.ArgumentParser(
        description="Export a build123d-generated STL as a multi-colour 3MF."
    )
    parser.add_argument("stl", help="Input STL file path")
    parser.add_argument(
        "--layer-height",
        type=float,
        default=0.2,
        help="Layer height in mm (default: 0.2)",
    )
    parser.add_argument(
        "--colors",
        nargs="+",
        default=["#FF0000", "#0000FF"],
        help='Hex colours for alternating layers (default: "#FF0000" "#0000FF")',
    )
    parser.add_argument(
        "-o", "--output",
        default=None,
        help="Output 3MF file path (default: input with .3mf extension)",
    )
    parser.add_argument(
        "--tolerance",
        type=float,
        default=0.01,
        help="Tessellation tolerance in mm (default: 0.01)",
    )
    args = parser.parse_args()

    # For standalone use, load STL via lib3mf, read triangles, then re-export
    # with per-triangle materials.
    wrapper = lib3mf.get_wrapper()
    reader_model = wrapper.CreateModel()
    reader = reader_model.QueryReader("stl")
    reader.ReadFromFile(args.stl)

    # Get the mesh object
    obj_iter = reader_model.GetMeshObjects()
    if not obj_iter.MoveNext():
        raise RuntimeError(f"No mesh found in {args.stl}")
    stl_mesh = obj_iter.GetCurrentMeshObject()

    # Extract vertices and faces
    vert_count = stl_mesh.GetVertexCount()
    tri_count = stl_mesh.GetTriangleCount()
    vertices_raw = []
    for i in range(vert_count):
        v = stl_mesh.GetVertex(i)
        vertices_raw.append(v)
    faces_raw = []
    for i in range(tri_count):
        t = stl_mesh.GetTriangle(i)
        faces_raw.append(t)

    # Build new model with materials
    model = wrapper.CreateModel()
    mesh = model.AddMeshObject()
    mesh.SetName("part")
    mesh.SetGeometry(vertices_raw, faces_raw)

    # Create material group
    mat_group = model.AddBaseMaterialGroup()
    mat_indices = []
    for i, hex_color in enumerate(args.colors):
        r, g, b = _hex_to_rgb(hex_color)
        color = wrapper.RGBAToColor(r, g, b, 255)
        mat_indices.append(mat_group.AddMaterial(f"Color{i}", color))
    mat_id = mat_group.GetResourceID()

    # Assign per-triangle materials
    for i in range(tri_count):
        t = faces_raw[i]
        v0 = vertices_raw[t.Indices[0]]
        v1 = vertices_raw[t.Indices[1]]
        v2 = vertices_raw[t.Indices[2]]
        z_centroid = (
            v0.Coordinates[2] + v1.Coordinates[2] + v2.Coordinates[2]
        ) / 3.0
        layer_index = int(z_centroid / args.layer_height)
        prop_id = mat_indices[layer_index % len(args.colors)]

        props = lib3mf.TriangleProperties()
        props.ResourceID = mat_id
        props.PropertyIDs[0] = prop_id
        props.PropertyIDs[1] = prop_id
        props.PropertyIDs[2] = prop_id
        mesh.SetTriangleProperties(i, props)

    mesh.SetObjectLevelProperty(mat_id, mat_indices[0])
    model.AddBuildItem(mesh, wrapper.GetIdentityTransform())

    output = args.output or args.stl.rsplit(".", 1)[0] + ".3mf"
    writer = model.QueryWriter("3mf")
    writer.WriteToFile(output)
    print(f"Exported: {output} ({tri_count} triangles, {len(args.colors)} colours, {args.layer_height}mm layers)")


if __name__ == "__main__":
    main()
