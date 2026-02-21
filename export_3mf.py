"""Export build123d parts as multi-color 3MF files with alternating layer colors.

Produces a single manifold mesh (via STL round-trip through OCCT) and writes
per-triangle paint_color attributes into the 3MF XML.  These are read
natively by OrcaSlicer and Bambu Studio as filament painting data.
"""

import argparse
import os
import tempfile
import xml.etree.ElementTree as ET
import zipfile

import lib3mf


def _hex_to_rgb(hex_str: str) -> tuple[int, int, int]:
    """Convert '#RRGGBB' to (R, G, B) ints."""
    h = hex_str.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _encode_paint_color(extruder_idx: int) -> str:
    """Encode an extruder index (0-based) as a paint_color hex string.

    BambuStudio/OrcaSlicer TriangleSelector bitstream format (4 bits):
      bits[0:1] = 00  (leaf node marker)
      bits[2:3] = state  (1=Extruder1, 2=Extruder2, ...)
    Reassembled as hex: (state << 2).
      Extruder 0 → "4", Extruder 1 → "8"
    """
    state = extruder_idx + 1
    return format(state << 2, "X")


def _read_stl_mesh(stl_path):
    """Read an STL file via lib3mf, return (vertices, faces) lists."""
    wrapper = lib3mf.get_wrapper()
    reader_model = wrapper.CreateModel()
    reader = reader_model.QueryReader("stl")
    reader.ReadFromFile(stl_path)

    obj_iter = reader_model.GetMeshObjects()
    if not obj_iter.MoveNext():
        raise RuntimeError(f"No mesh found in {stl_path}")
    stl_mesh = obj_iter.GetCurrentMeshObject()

    vert_count = stl_mesh.GetVertexCount()
    tri_count = stl_mesh.GetTriangleCount()
    return (
        [stl_mesh.GetVertex(i) for i in range(vert_count)],
        [stl_mesh.GetTriangle(i) for i in range(tri_count)],
    )


def _write_basic_3mf(vertices, faces, out_path):
    """Write a plain single-mesh 3MF (no materials) via lib3mf."""
    wrapper = lib3mf.get_wrapper()
    model = wrapper.CreateModel()
    mesh = model.AddMeshObject()
    mesh.SetName("part")
    mesh.SetGeometry(vertices, faces)
    model.AddBuildItem(mesh, wrapper.GetIdentityTransform())
    writer = model.QueryWriter("3mf")
    writer.WriteToFile(out_path)


def _compute_tri_colors(vertices, faces, layer_height, num_colors):
    """Return list of 0-based color index per triangle, by Z centroid."""
    result = []
    for t in faces:
        v0 = vertices[t.Indices[0]]
        v1 = vertices[t.Indices[1]]
        v2 = vertices[t.Indices[2]]
        z = (v0.Coordinates[2] + v1.Coordinates[2] + v2.Coordinates[2]) / 3.0
        layer_idx = int(z / layer_height)
        result.append(layer_idx % num_colors)
    return result


NS_3MF = "http://schemas.microsoft.com/3dmanufacturing/core/2015/02"


def _inject_paint_colors(tmf_path, tri_colors, out_path):
    """Post-process a 3MF: add paint_color attrs to triangles."""
    with zipfile.ZipFile(tmf_path, "r") as zin:
        model_xml = zin.read("3D/3dmodel.model")
        other_files = {}
        for name in zin.namelist():
            if name != "3D/3dmodel.model":
                other_files[name] = zin.read(name)

    # Register the 3MF default namespace so ET doesn't add ns0: prefixes
    ET.register_namespace("", NS_3MF)
    # Preserve other namespaces lib3mf may have written
    for prefix, uri in [
        ("m", "http://schemas.microsoft.com/3dmanufacturing/material/2015/02"),
        ("p", "http://schemas.microsoft.com/3dmanufacturing/production/2015/06"),
    ]:
        ET.register_namespace(prefix, uri)

    root = ET.fromstring(model_xml)

    # Add paint_color attribute to each triangle
    tri_idx = 0
    for tri_elem in root.iter(f"{{{NS_3MF}}}triangle"):
        if tri_idx < len(tri_colors):
            color_idx = tri_colors[tri_idx]
            tri_elem.set("paint_color", _encode_paint_color(color_idx))
            tri_idx += 1

    # Add BambuStudio painting version metadata
    meta = ET.SubElement(root, f"{{{NS_3MF}}}metadata")
    meta.set("name", "BambuStudio:MmPaintingVersion")
    meta.text = "0"

    new_xml = ET.tostring(root, encoding="unicode", xml_declaration=True)

    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zout:
        zout.writestr("3D/3dmodel.model", new_xml)
        for name, data in other_files.items():
            zout.writestr(name, data)


def export_multicolor_3mf(
    part,
    filename: str,
    layer_height: float,
    colors: list[str] | None = None,
) -> None:
    """Export a build123d Part as a 3MF with alternating layer colours.

    Uses STL round-trip for a manifold mesh, then injects per-triangle
    paint_color attributes for native OrcaSlicer/Bambu Studio support.

    Args:
        part: A build123d Part (or Shape).
        filename: Output .3mf file path.
        layer_height: Print layer height in mm.
        colors: Hex colour strings (e.g. ["#FF0000", "#0000FF"]).
                Defaults to red and blue if not supplied.
    """
    if colors is None:
        colors = ["#FF0000", "#0000FF"]
    if len(colors) < 2:
        raise ValueError("Need at least two colours for alternating layers")

    from build123d import export_stl

    with tempfile.NamedTemporaryFile(suffix=".stl", delete=False) as tmp:
        tmp_stl = tmp.name
    export_stl(part, tmp_stl)

    vertices, faces = _read_stl_mesh(tmp_stl)
    os.unlink(tmp_stl)

    tri_colors = _compute_tri_colors(vertices, faces, layer_height, len(colors))

    with tempfile.NamedTemporaryFile(suffix=".3mf", delete=False) as tmp:
        tmp_3mf = tmp.name
    _write_basic_3mf(vertices, faces, tmp_3mf)
    _inject_paint_colors(tmp_3mf, tri_colors, filename)
    os.unlink(tmp_3mf)


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
    args = parser.parse_args()

    vertices, faces = _read_stl_mesh(args.stl)
    tri_colors = _compute_tri_colors(
        vertices, faces, args.layer_height, len(args.colors)
    )

    with tempfile.NamedTemporaryFile(suffix=".3mf", delete=False) as tmp:
        tmp_3mf = tmp.name
    _write_basic_3mf(vertices, faces, tmp_3mf)

    output = args.output or args.stl.rsplit(".", 1)[0] + ".3mf"
    _inject_paint_colors(tmp_3mf, tri_colors, output)
    os.unlink(tmp_3mf)

    print(f"Exported: {output} ({len(faces)} triangles, {len(args.colors)} colours, {args.layer_height}mm layers)")


if __name__ == "__main__":
    main()
