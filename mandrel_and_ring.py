"""Generate 3D-printable mandrel and decorative ring using build123d."""

import argparse

from build123d import (
    Align,
    Axis,
    BuildLine,
    BuildPart,
    BuildSketch,
    Cone,
    Cylinder,
    Line,
    Locations,
    Mode,
    Plane,
    ThreePointArc,
    export_stl,
    fillet,
    make_face,
    revolve,
)


def build_mandrel(
    cylinder_dia: float,
    cylinder_length: float,
    taper_end_dia: float,
    taper_length: float,
) -> "Part":
    """Build a mandrel: cylinder segment + tapered cone."""
    with BuildPart() as mandrel:
        # Cylindrical segment, bottom-aligned
        Cylinder(
            radius=cylinder_dia / 2,
            height=cylinder_length,
            align=(Align.CENTER, Align.CENTER, Align.MIN),
        )
        # Tapered section on top of the cylinder
        with Locations([(0, 0, cylinder_length)]):
            Cone(
                bottom_radius=cylinder_dia / 2,
                top_radius=taper_end_dia / 2,
                height=taper_length,
                align=(Align.CENTER, Align.CENTER, Align.MIN),
            )
    return mandrel.part


def build_ring(
    inner_dia: float,
    thickness: float,
    height: float,
    fillet_radius: float,
    groove_od: float,
    small_flare: bool = True,
) -> "Part":
    """Build a decorative ring: two stacked segments with a groove between them.

    Bottom segment is full OD, top segment is 2/3 OD, both equal height.
    A groove at the junction narrows to half wall thickness (1/2 max OD),
    with fillets curving inward from each segment. The cross-section profile
    is filleted in 2D then revolved for clean geometry.
    """
    inner_radius = inner_dia / 2
    outer_radius = inner_radius + thickness
    small_outer_radius = inner_radius + thickness * 2 / 3
    groove_radius = groove_od / 2
    seg_height = height / 2

    fr = fillet_radius * seg_height  # scale fillet with segment height

    with BuildPart() as ring:
        with BuildSketch(Plane.XZ) as profile:
            with BuildLine():
                # Bottom edge: bore to fillet start
                Line((inner_radius, 0), (outer_radius - fr, 0))
                # Bottom-right corner arc
                ThreePointArc(
                    (outer_radius - fr, 0),
                    (outer_radius, fr * 0.293),
                    (outer_radius, fr),
                )
                # Right side of lower segment up to groove
                Line((outer_radius, fr), (outer_radius, seg_height - fr))
                # Groove: arc from large OD curving in to groove bottom
                ThreePointArc(
                    (outer_radius, seg_height - fr),
                    ((outer_radius + groove_radius) / 2, seg_height),
                    (groove_radius, seg_height),
                )
                # Groove: arc from groove bottom curving out to small OD
                ThreePointArc(
                    (groove_radius, seg_height),
                    ((groove_radius + small_outer_radius) / 2, seg_height),
                    (small_outer_radius, seg_height + fr),
                )
                if small_flare:
                    # Truncate small ring at 3/4 total height — flares out, no top fillet
                    top_z = height * 3 / 4
                    Line(
                        (small_outer_radius, seg_height + fr),
                        (small_outer_radius, top_z),
                    )
                    # Flat top from small OD back to bore
                    Line((small_outer_radius, top_z), (inner_radius, top_z))
                else:
                    # Full height small ring with top fillet
                    Line(
                        (small_outer_radius, seg_height + fr),
                        (small_outer_radius, 2 * seg_height - fr),
                    )
                    ThreePointArc(
                        (small_outer_radius, 2 * seg_height - fr),
                        (small_outer_radius, 2 * seg_height - fr * 0.293),
                        (small_outer_radius - fr, 2 * seg_height),
                    )
                    Line((small_outer_radius - fr, 2 * seg_height), (inner_radius, 2 * seg_height))
                # Bore side
                actual_top = height * 3 / 4 if small_flare else 2 * seg_height
                Line((inner_radius, actual_top), (inner_radius, 0))
            make_face()
        revolve(axis=Axis.Z)

    return ring.part


def main():
    parser = argparse.ArgumentParser(
        description="Generate 3D-printable mandrel and decorative ring."
    )
    # Ring parameters
    parser.add_argument("--ring-id", type=float, default=8.5, help="Ring inner diameter in mm (default: 8.5)")
    parser.add_argument("--ring-thickness", type=float, default=2.175, help="Ring wall thickness in mm (default: 2.175)")
    parser.add_argument("--ring-height", type=float, default=4.0, help="Ring height in mm (default: 4.0)")
    parser.add_argument("--fillet-radius", type=float, default=0.4, help="Fillet radius as proportion of segment height (default: 0.4)")
    parser.add_argument("--groove-od", type=float, default=None, help="Groove OD in mm (default: midpoint of bore and small OD)")
    parser.add_argument("--no-small-flare", action="store_true", help="Disable small ring flare (default: flare enabled)")
    # Mandrel parameters
    parser.add_argument("--mandrel-dia", type=float, default=9.0, help="Mandrel cylinder diameter in mm (default: 9.0)")
    parser.add_argument("--mandrel-cyl-length", type=float, default=25.0, help="Mandrel cylinder length in mm (default: 25.0)")
    parser.add_argument("--taper-end-dia", type=float, default=8.0, help="Taper end diameter in mm (default: 8.0)")
    parser.add_argument("--taper-length", type=float, default=30.0, help="Taper length in mm (default: 30.0)")
    # Display
    parser.add_argument("--no-view", action="store_true", help="Skip ocp_vscode display")

    args = parser.parse_args()

    # Build parts
    mandrel = build_mandrel(
        cylinder_dia=args.mandrel_dia,
        cylinder_length=args.mandrel_cyl_length,
        taper_end_dia=args.taper_end_dia,
        taper_length=args.taper_length,
    )

    # Compute groove OD default if not specified
    inner_radius = args.ring_id / 2
    small_outer_radius = inner_radius + args.ring_thickness * 2 / 3
    groove_od = args.groove_od if args.groove_od is not None else (inner_radius + small_outer_radius)

    ring = build_ring(
        inner_dia=args.ring_id,
        thickness=args.ring_thickness,
        height=args.ring_height,
        fillet_radius=args.fillet_radius,
        groove_od=groove_od,
        small_flare=not args.no_small_flare,
    )

    # Export STL files
    export_stl(mandrel, "mandrel.stl")
    export_stl(ring, "ring.stl")

    # Print summary
    outer_dia = args.ring_id + 2 * args.ring_thickness
    small_od = args.ring_id + 2 * args.ring_thickness * 2 / 3
    rid = args.ring_id
    total_mandrel = args.mandrel_cyl_length + args.taper_length

    print(f"Mandrel: {args.mandrel_dia}mm dia × {args.mandrel_cyl_length}mm cyl + taper {args.mandrel_dia}→{args.taper_end_dia}mm × {args.taper_length}mm = {total_mandrel}mm total")
    print(f"Ring:")
    print(f"  ID         = {rid:.2f}mm")
    print(f"  OD         = {outer_dia:.2f}mm  (wall {(outer_dia - rid) / 2:.2f}mm)")
    print(f"  Small OD   = {small_od:.2f}mm  (wall {(small_od - rid) / 2:.2f}mm)")
    print(f"  Groove OD  = {groove_od:.2f}mm  (wall {(groove_od - rid) / 2:.2f}mm)")
    small_flare = not args.no_small_flare
    actual_height = args.ring_height * 3 / 4 if small_flare else args.ring_height
    print(f"  Height     = {actual_height:.2f}mm" + (f"  (flared, truncated from {args.ring_height:.2f}mm)" if small_flare else ""))
    print(f"  Fillet     = {args.fillet_radius} × seg height")
    print(f"  Small flare = {'on' if small_flare else 'off'}")
    print("Exported: mandrel.stl, ring.stl")

    # Show in ocp_vscode if available
    if not args.no_view:
        try:
            from ocp_vscode import show

            show(mandrel, ring, names=["Mandrel", "Ring"], colors=["steelblue", "gold"])
            print("Displayed in OCP viewer")
        except Exception:
            print("OCP viewer not available, skipping display")


if __name__ == "__main__":
    main()
