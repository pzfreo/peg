"""Generate a 3D-printable peg holder for turning violin/cello pegs on a lathe.

The holder has a plain cylindrical exterior (for lathe chuck grip) and a
tapered interior hole sized to hold a peg. The taper ratio (e.g. 1:30)
means the diameter increases by 1mm for every 30mm of length.
"""

import argparse

from build123d import (
    Align,
    Axis,
    BuildLine,
    BuildPart,
    BuildSketch,
    Cylinder,
    Line,
    Locations,
    Mode,
    Plane,
    Text,
    export_stl,
    extrude,
    make_face,
    revolve,
)


def build_holder(
    small_end_dia: float,
    taper_ratio: float,
    length: float,
    wall_thickness: float,
    label_depth: float = 2.0,
) -> "Part":
    """Build a peg holder: plain cylinder with tapered bore.

    Args:
        small_end_dia: Diameter of the small (entry) end of the taper in mm.
        taper_ratio: Taper ratio — diameter increases 1mm per this many mm of length.
        length: Total holder length in mm.
        wall_thickness: Wall thickness around the large end of the taper in mm.
    """
    small_radius = small_end_dia / 2
    large_radius = small_radius + length / taper_ratio / 2
    outer_radius = large_radius + wall_thickness

    # Build using a revolved cross-section for the tapered bore
    with BuildPart() as holder:
        with BuildSketch(Plane.XZ) as profile:
            with BuildLine():
                # Outer profile (bottom = large end, top = small end)
                Line((0, 0), (outer_radius, 0))          # bottom edge
                Line((outer_radius, 0), (outer_radius, length))  # outer wall
                Line((outer_radius, length), (0, length))  # top edge
                Line((0, length), (0, 0))                  # center axis
            make_face()
        revolve(axis=Axis.Z)

        # Subtract the tapered bore using a revolved taper profile
        with BuildSketch(Plane.XZ) as bore_profile:
            with BuildLine():
                Line((0, 0), (large_radius, 0))           # large end
                Line((large_radius, 0), (small_radius, length))  # taper wall
                Line((small_radius, length), (0, length))  # top center
                Line((0, length), (0, 0))                  # center axis
            make_face()
        revolve(axis=Axis.Z, mode=Mode.SUBTRACT)

        # Engrave taper ratio label on the large end face (z=0)
        label_text = f"1:{taper_ratio:.0f}"
        mid_radius = (large_radius + outer_radius) / 2
        font_size = (outer_radius - large_radius) * 0.5
        # Place text on the large end face, readable from outside (looking in -Z)
        from build123d import Location, Vector
        mirror_plane = Plane(origin=(0, 0, 0), x_dir=(1, 0, 0), z_dir=(0, 0, -1))
        with BuildSketch(mirror_plane) as lbl:
            loc = Location(Vector(0, mid_radius, 0))
            with Locations([loc]):
                Text(label_text, font_size=font_size)
        extrude(amount=-label_depth, mode=Mode.SUBTRACT)

    return holder.part


def main():
    parser = argparse.ArgumentParser(
        description="Generate a 3D-printable peg holder for lathe turning."
    )
    parser.add_argument("--small-end-dia", type=float, default=7.0, help="Small end diameter of taper in mm (default: 7.0)")
    parser.add_argument("--taper-ratio", type=float, default=30.0, help="Taper ratio: dia grows 1mm per this many mm (default: 30)")
    parser.add_argument("--length", type=float, default=40.0, help="Holder length in mm (default: 40)")
    parser.add_argument("--wall-thickness", type=float, default=5.0, help="Wall thickness in mm (default: 5.0)")
    parser.add_argument("--no-view", action="store_true", help="Skip ocp_vscode display")

    args = parser.parse_args()

    holder = build_holder(
        small_end_dia=args.small_end_dia,
        taper_ratio=args.taper_ratio,
        length=args.length,
        wall_thickness=args.wall_thickness,
    )

    # Print summary
    large_dia = args.small_end_dia + args.length / args.taper_ratio
    outer_dia = large_dia + 2 * args.wall_thickness

    filename = f"peg_holder_1-{args.taper_ratio:.0f}_{args.small_end_dia:.1f}mm.stl"
    export_stl(holder, filename)

    print("Peg Holder:")
    print(f"  Length       = {args.length:.2f}mm")
    print(f"  Taper ratio  = 1:{args.taper_ratio:.0f}")
    print(f"  Small end ID = {args.small_end_dia:.2f}mm")
    print(f"  Large end ID = {large_dia:.2f}mm")
    print(f"  Outer dia    = {outer_dia:.2f}mm  (wall {args.wall_thickness:.2f}mm)")
    print(f"Exported: {filename}")

    if not args.no_view:
        try:
            from ocp_vscode import show
            from ocp_vscode import config as _ocp_cfg

            # Fix version mismatch: viewer returns int enum values but library expects str keys
            for i, collapse in enumerate(_ocp_cfg.Collapse):
                _ocp_cfg.COLLAPSE_REVERSE_MAPPING[i] = collapse

            show(holder, names=["Peg Holder"], colors=["sienna"])
            print("Displayed in OCP viewer")
        except ImportError:
            print("OCP viewer not available, skipping display")


if __name__ == "__main__":
    main()
