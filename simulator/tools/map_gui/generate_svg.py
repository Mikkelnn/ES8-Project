"""
generate_svg.py
---------------
Reads node_outputs.json and writes a validation SVG.

All file I/O defaults to the current working directory (CWD) so that
node_generation.py, generate_svg.py, displayed_gui.py and all their
inputs/outputs live in the same directory without any path configuration.

Usage
-----
# Called automatically by node_generation.py — no action needed.

# Standalone regeneration from an existing JSON:
    python generate_svg.py
    python generate_svg.py --input node_outputs.json --output node_outputs.svg

Visual encoding
---------------
- One colour per road (consistent with node_generation.py)
- Coloured lines  = road neighbour edges
- Coloured dots   = road sample nodes
- White ring      = single-source intersection node
- Gold ring       = merged intersection node (2+ sources)
- White lines     = intersection → neighbour arms
- Legend          = road colours + symbols + merge/interval values
"""

import json
import sys
import argparse
from pathlib import Path

# ── Colour palette (road_id → hex) ───────────────────────────────────────────
ROAD_COLORS: dict = {
    "7989326":   "#38bdf8",
    "10059631":  "#fb923c",
    "10059633":  "#a3e635",
    "10240023":  "#f472b6",
    "25660118":  "#facc15",
    "25660119":  "#c084fc",
    "28265154":  "#34d399",
    "30628498":  "#f87171",
    "30640093":  "#22d3ee",
    "30660405":  "#fbbf24",
    "88590401":  "#86efac",
    "144315489": "#ff6fd8",
}

# ── Node / edge sizes (SVG coordinate units) ──────────────────────────────────
R_ROAD     = 0.045
R_INT      = 0.13
R_INT_C    = 0.055
EDGE_W     = 0.018
INT_EDGE_W = 0.032


def generate_svg(
    input_path:  str = "node_outputs.json",
    output_path: str = "node_outputs.svg",
) -> None:
    """
    Read *input_path* and write a validation SVG to *output_path*.

    Relative paths are resolved against the current working directory so
    that placing all project files in one folder always works without
    any extra path configuration.
    """
    # Resolve relative to CWD so the script works from any working directory
    inp = Path(input_path)
    if not inp.is_absolute():
        inp = Path(__file__).resolve().parent / inp
    inp = inp.resolve()

    if not inp.exists():
        raise FileNotFoundError(f"Input not found: {inp}")

    with inp.open(encoding="utf-8") as fh:
        data = json.load(fh)

    nodes    = data["nodes"]
    gateways = data.get("gateways", {})
    meta     = data.get("metadata", {})
    merge_r  = meta.get("merge_radius_m", "?")
    interval = meta.get("target_interval_m", 12.5)

    # ── viewBox ───────────────────────────────────────────────────────────────
    all_x = [n["point"][0] for n in nodes.values()]
    all_y = [n["point"][1] for n in nodes.values()]
    pad   = 0.4
    vbx   = min(all_x) - pad
    vby   = min(all_y) - pad
    vbw   = max(all_x) - min(all_x) + 2 * pad
    vbh   = max(all_y) - min(all_y) + 2 * pad

    SVG_W = 1600
    SVG_H = int(SVG_W / (vbw / vbh))

    road_ids  = sorted({n["road_id"] for n in nodes.values() if n["road_id"]})
    int_nodes = {nid: n for nid, n in nodes.items() if n["intersection_id"]}

    gateway_points = []
    if isinstance(gateways, dict):
        for gid, g in gateways.items():
            point = g.get("point") if isinstance(g, dict) else None
            if not isinstance(point, list) or len(point) < 2:
                continue
            try:
                x = float(point[0])
                y = float(point[1])
            except (TypeError, ValueError):
                continue
            gateway_points.append((str(gid), x, y))

    # ── Build SVG ─────────────────────────────────────────────────────────────
    L = []
    L.append('<?xml version="1.0" encoding="UTF-8"?>')
    L.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'viewBox="{vbx:.4f} {vby:.4f} {vbw:.4f} {vbh:.4f}" '
        f'width="{SVG_W}" height="{SVG_H}" '
        f'style="background:#080d14;">'
    )

    # Defs
    L.append("<defs>")
    for rid in road_ids:
        L.append(
            f'  <filter id="rg_{rid}" x="-60%" y="-60%" width="220%" height="220%">'
            f'<feGaussianBlur stdDeviation="0.018" result="b"/>'
            f'<feMerge><feMergeNode in="b"/>'
            f'<feMergeNode in="SourceGraphic"/></feMerge></filter>'
        )
    L.append(
        '  <filter id="iglow" x="-150%" y="-150%" width="400%" height="400%">'
        '<feGaussianBlur stdDeviation="0.07" result="b"/>'
        '<feMerge><feMergeNode in="b"/>'
        '<feMergeNode in="SourceGraphic"/></feMerge></filter>'
    )
    L.append(
        '  <filter id="mglow" x="-150%" y="-150%" width="400%" height="400%">'
        '<feGaussianBlur stdDeviation="0.10" result="b"/>'
        '<feMerge><feMergeNode in="b"/>'
        '<feMergeNode in="SourceGraphic"/></feMerge></filter>'
    )
    L.append(
        '  <filter id="gglow" x="-150%" y="-150%" width="400%" height="400%">'
        '<feGaussianBlur stdDeviation="0.07" result="b"/>'
        '<feMerge><feMergeNode in="b"/>'
        '<feMergeNode in="SourceGraphic"/></feMerge></filter>'
    )
    L.append("</defs>")

    # Layer 1 — road neighbour edges
    for rid in road_ids:
        col   = ROAD_COLORS.get(rid, "#aaaaaa")
        edges = []
        for nid, n in nodes.items():
            if n["road_id"] != rid:
                continue
            x1, y1 = n["point"]
            for nb_nid in n["neighbours"]:
                if int(nb_nid) < int(nid):
                    continue
                nb = nodes.get(nb_nid)
                if nb is None:
                    continue
                x2, y2 = nb["point"]
                edges.append(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}"/>')
        if edges:
            L.append(f'<g stroke="{col}" stroke-width="{EDGE_W}" opacity="0.40">')
            L.extend(edges)
            L.append("</g>")

    # Layer 2 — intersection → neighbour edges
    int_edges = []
    for nid, n in int_nodes.items():
        x1, y1 = n["point"]
        for nb_nid in n["neighbours"]:
            if int(nb_nid) < int(nid):
                continue
            nb = nodes.get(nb_nid)
            if nb is None:
                continue
            x2, y2 = nb["point"]
            int_edges.append(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}"/>')
    if int_edges:
        L.append(f'<g stroke="#ffffff" stroke-width="{INT_EDGE_W}" opacity="0.55">')
        L.extend(int_edges)
        L.append("</g>")

    # Layer 3 — road sample dots
    for rid in road_ids:
        col  = ROAD_COLORS.get(rid, "#aaaaaa")
        dots = []
        for nid, n in nodes.items():
            if n["road_id"] != rid:
                continue
            x, y = n["point"]
            dots.append(f'<circle cx="{x}" cy="{y}" r="{R_ROAD}"/>')
        if dots:
            L.append(f'<g fill="{col}" opacity="0.92" filter="url(#rg_{rid})">')
            L.extend(dots)
            L.append("</g>")

    # Layer 4 — intersection nodes
    for nid, n in int_nodes.items():
        x, y   = n["point"]
        src    = n.get("source_intersection_ids") or []
        merged = len(src) > 1
        rc     = "#fbbf24" if merged else "#ffffff"
        gid    = "mglow"   if merged else "iglow"
        sw     = 0.045     if merged else 0.032

        L.append(f'<g filter="url(#{gid})">')
        L.append(f'  <circle cx="{x}" cy="{y}" r="{R_INT*2.0}" fill="{rc}0d"/>')
        L.append(
            f'  <circle cx="{x}" cy="{y}" r="{R_INT}" fill="none" '
            f'stroke="{rc}" stroke-width="{sw}"/>'
        )
        L.append(f'  <circle cx="{x}" cy="{y}" r="{R_INT_C}" fill="{rc}"/>')
        L.append("</g>")

    # Layer 5 - gateway nodes
    if gateway_points:
        gw_color = "#22d3ee"
        for _, x, y in gateway_points:
            L.append('<g filter="url(#gglow)">')
            L.append(f'  <circle cx="{x}" cy="{y}" r="{R_INT*2.0}" fill="{gw_color}0d"/>')
            L.append(
                f'  <circle cx="{x}" cy="{y}" r="{R_INT}" fill="none" '
                f'stroke="{gw_color}" stroke-width="0.032"/>'
            )
            L.append(f'  <circle cx="{x}" cy="{y}" r="{R_INT_C}" fill="{gw_color}"/>')
            L.append("</g>")

    # Layer 6 — legend
    lx    = vbx + 0.15
    ly    = vby + 0.22
    ts    = 0.17
    dr    = 0.07
    rh    = 0.28
    bw    = 3.8
    box_h = (len(road_ids) + 5) * rh + 0.25

    L.append('<g id="legend">')
    L.append(
        f'<rect x="{lx-0.12:.3f}" y="{ly-0.22:.3f}" width="{bw}" '
        f'height="{box_h:.3f}" fill="#080d14" fill-opacity="0.80" rx="0.10"/>'
    )
    L.append(
        f'<text x="{lx+0.05:.3f}" y="{ly:.3f}" font-size="{ts*1.05}" '
        f'fill="#ffffff" font-weight="bold" font-family="monospace">'
        f"Node map  (merge r={merge_r} m, interval={interval} m)</text>"
    )
    ly += rh * 1.1

    for rid in road_ids:
        col = ROAD_COLORS.get(rid, "#aaa")
        L.append(f'<circle cx="{lx+dr:.3f}" cy="{ly-dr*0.6:.3f}" r="{dr}" fill="{col}"/>')
        L.append(
            f'<text x="{lx+dr*2.8:.3f}" y="{ly:.3f}" font-size="{ts*0.82}" '
            f'fill="{col}" font-family="monospace">road {rid}</text>'
        )
        ly += rh

    L.append(
        f'<line x1="{lx:.3f}" y1="{ly-rh*0.3:.3f}" '
        f'x2="{lx+bw-0.3:.3f}" y2="{ly-rh*0.3:.3f}" '
        f'stroke="#ffffff22" stroke-width="0.015"/>'
    )
    L.append(
        f'<circle cx="{lx+dr:.3f}" cy="{ly-dr*0.6:.3f}" r="{dr*1.6}" '
        f'fill="none" stroke="#ffffff" stroke-width="0.022"/>'
    )
    L.append(f'<circle cx="{lx+dr:.3f}" cy="{ly-dr*0.6:.3f}" r="{dr*0.55}" fill="#ffffff"/>')
    L.append(
        f'<text x="{lx+dr*2.8:.3f}" y="{ly:.3f}" font-size="{ts*0.82}" '
        f'fill="#ffffff" font-family="monospace">intersection node</text>'
    )
    ly += rh
    L.append(
        f'<circle cx="{lx+dr:.3f}" cy="{ly-dr*0.6:.3f}" r="{dr*1.6}" '
        f'fill="none" stroke="#fbbf24" stroke-width="0.028"/>'
    )
    L.append(f'<circle cx="{lx+dr:.3f}" cy="{ly-dr*0.6:.3f}" r="{dr*0.55}" fill="#fbbf24"/>')
    L.append(
        f'<text x="{lx+dr*2.8:.3f}" y="{ly:.3f}" font-size="{ts*0.82}" '
        f'fill="#fbbf24" font-family="monospace">merged intersection</text>'
    )
    ly += rh
    L.append(
        f'<circle cx="{lx+dr:.3f}" cy="{ly-dr*0.6:.3f}" r="{dr*1.35}" '
        f'fill="#22d3ee0d" stroke="#22d3ee" stroke-width="0.022"/>'
    )
    L.append(f'<circle cx="{lx+dr:.3f}" cy="{ly-dr*0.6:.3f}" r="{dr*0.55}" fill="#22d3ee"/>')
    L.append(
        f'<text x="{lx+dr*2.8:.3f}" y="{ly:.3f}" font-size="{ts*0.82}" '
        f'fill="#22d3ee" font-family="monospace">gateway point</text>'
    )
    L.append("</g>")
    L.append("</svg>")

    svg = "\n".join(L)

    import xml.etree.ElementTree as ET
    ET.fromstring(svg)  # validate

    # Resolve output against CWD
    out = Path(output_path)
    if not out.is_absolute():
        out = Path(__file__).resolve().parent / out
    out = out.resolve()

    out.write_text(svg, encoding="utf-8")

    n_int    = len(int_nodes)
    n_merged = sum(
        1 for n in int_nodes.values()
        if len(n.get("source_intersection_ids") or []) > 1
    )
    n_gateways = len(gateway_points)
    print(
        f"SVG written -> {out}  "
        f"({len(svg)//1024} KB, {SVG_W}x{SVG_H}px)  "
        f"{len(nodes)} nodes  |  {n_int} intersection nodes  "
        f"({n_merged} merged)  |  {n_gateways} gateways"
    )


# ── CLI ───────────────────────────────────────────────────────────────────────
def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate a validation SVG from node_outputs.json.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--input", "-i",
        default="node_outputs.json",
        help="Path to node_outputs.json (relative = resolved from CWD).",
    )
    parser.add_argument(
        "--output", "-o",
        default="node_outputs.svg",
        help="Destination SVG file path (relative = resolved from CWD).",
    )
    args = parser.parse_args()
    generate_svg(input_path=args.input, output_path=args.output)


if __name__ == "__main__":
    main()
