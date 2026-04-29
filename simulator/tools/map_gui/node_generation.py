"""
generate_nodes.py
-----------------
Input  : selected_roads.json
Output : node_outputs.json  +  node_outputs.svg

Sampling algorithm (uniform division)
--------------------------------------
For each road segment between two endpoints (intersection-to-intersection,
intersection-to-terminal, or terminal-to-terminal):

  1. Measure the true arc-length of the segment in metres.
  2. n = ceil(arc_length / 12.5)           <- number of equal divisions
  3. spacing = arc_length / n               <- actual uniform spacing (≤ 12.5 m)
  4. Place (n - 1) interior nodes at arc positions:
         spacing, 2·spacing, …, (n-1)·spacing
     measured from the segment start.

This guarantees:
  - Every gap in a segment is identical (uniform).
  - No remainder is ever dropped or left over.
  - Spacing is as close to 12.5 m as possible while dividing exactly.
  - Segments shorter than 12.5 m get spacing = arc_length (0 interior nodes,
    just the two endpoint nodes connected directly).

Projection
----------
SVG X and Y have different metres-per-unit values:
  m_per_svg_x ≈  84.11 m/unit  (longitude axis)
  m_per_svg_y ≈ 151.78 m/unit  (latitude axis)
All metric distances use the correct per-axis conversion.
"""

import json, math, re
from pathlib import Path
from collections import defaultdict
# Ensure generate_svg.py is importable from the same directory as this script
import sys as _sys
_sys.path.insert(0, str(Path(__file__).resolve().parent))
from generate_svg import generate_svg
from datetime import datetime
import os
import numpy as np
import tqdm 

# ── Configurable ─────────────────────────────────────────────────────────────
INTERVAL_M     = 12.5
MERGE_RADIUS_M = 12.5   # set 0 to disable
STITCH_TOL     = 0.05   # SVG units — sub-path endpoint join tolerance
SNAP_TOL       = 0.05   # SVG units — max intersection-to-chain snap distance

# All I/O files are resolved against the directory this script lives in.
# Put selected_roads.json in the same folder as node_generation.py.
_CWD        = Path(__file__).resolve().parent
INPUT_FILE  = str(_CWD / "selected_roads.json")
PROCESSED_ROADS_JS = _CWD / "processedRoads.js"


def _load_scale_from_processed_roads_js(js_path=PROCESSED_ROADS_JS, m_per_svg_x_default=391.28702430863547, m_per_svg_y_default=702.5701092535716):
    """Read metadata.svg_dimensions.m_per_svg_x and m_per_svg_y from processedRoads.js and fall back to defaults."""
    if not js_path.exists():
        return [m_per_svg_x_default, m_per_svg_y_default]

    try:
        text = js_path.read_text(encoding="utf-8")
        match = re.search(r"const\s+\w+\s*=\s*(\{.*\});\s*$", text, re.DOTALL)
        if not match:
            return [m_per_svg_x_default, m_per_svg_y_default]

        payload = json.loads(match.group(1))
        metadata = payload.get("metadata", {})
        svg_dims = metadata.get("svg_dimensions", {})
        m_per_svg_x = svg_dims.get("m_per_svg_x")
        m_per_svg_y = svg_dims.get("m_per_svg_y")
        
        if m_per_svg_x is not None and m_per_svg_y is not None:
            return [float(m_per_svg_x), float(m_per_svg_y)]
        else:
            return [m_per_svg_x_default, m_per_svg_y_default]
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return [m_per_svg_x_default, m_per_svg_y_default]


# ── Projection constants ──────────────────────────────────────────────────────
_M_PER_SVG_SCALING    = _load_scale_from_processed_roads_js()
M_PER_SVG_X  = _M_PER_SVG_SCALING[0]
M_PER_SVG_Y  = _M_PER_SVG_SCALING[1]

result_dir = _CWD / "results" / datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
os.makedirs(result_dir, exist_ok=True)
OUTPUT_FILE = str(result_dir / "node_outputs.json")

# ── Distance helpers ──────────────────────────────────────────────────────────

def dist_m(a, b):
    """True metric distance in metres between two SVG-space points."""
    return math.hypot((b[0] - a[0]) * M_PER_SVG_X,
                      (b[1] - a[1]) * M_PER_SVG_Y)

def dist_svg(a, b):
    """Raw SVG Euclidean distance (used only for stitching / snapping)."""
    return math.hypot(b[0] - a[0], b[1] - a[1])

def lerp(a, b, t):
    return (a[0] + t * (b[0] - a[0]),
            a[1] + t * (b[1] - a[1]))

def chain_arc_m(chain):
    """Total metric arc-length of a polyline chain."""
    return sum(dist_m(chain[i], chain[i + 1]) for i in range(len(chain) - 1))


# ── SVG path parser ───────────────────────────────────────────────────────────

def parse_svg_path(d):
    polylines, current = [], []
    for token in d.split():
        if len(token) < 2:
            continue
        cmd, rest = token[0].upper(), token[1:]
        if cmd not in ("ML") or "," not in rest:
            continue
        parts = rest.split(",")
        if len(parts) != 2:
            continue
        try:
            x, y = float(parts[0]), float(parts[1])
        except ValueError:
            continue
        if cmd == "M":
            if current:
                polylines.append(current)
            current = [(x, y)]
        else:
            current.append((x, y))
    if current:
        polylines.append(current)
    return polylines


# ── Sub-path stitcher ─────────────────────────────────────────────────────────

def stitch(polylines, tol):
    chains = [list(p) for p in polylines]
    merged = True
    while merged:
        merged = False
        used, new_chains = [False] * len(chains), []
        for i in range(len(chains)):
            if used[i]:
                continue
            chain = chains[i]
            ext = True
            while ext:
                ext = False
                for j in range(len(chains)):
                    if used[j] or j == i:
                        continue
                    o = chains[j]
                    t, h = chain[-1], chain[0]
                    if   dist_svg(t, o[0])  <= tol: chain = chain + o[1:]
                    elif dist_svg(t, o[-1]) <= tol: chain = chain + list(reversed(o))[1:]
                    elif dist_svg(h, o[-1]) <= tol: chain = o + chain[1:]
                    elif dist_svg(h, o[0])  <= tol: chain = list(reversed(o)) + chain[1:]
                    else:
                        continue
                    used[j] = True; merged = True; ext = True
                    chains[i] = chain
                    break
            used[i] = True
            new_chains.append(chain)
        chains = new_chains
    return chains


# ── Vertex deduplication ──────────────────────────────────────────────────────

def deduplicate_chain(chain):
    """
    Remove consecutive vertices closer than INTERVAL_M metres.
    Eliminates near-duplicate M-command restarts in the raw SVG data.
    Always keeps the first and last vertex.
    """
    if len(chain) < 2:
        return chain
    clean = [chain[0]]
    for pt in chain[1:-1]:
        if dist_m(clean[-1], pt) >= INTERVAL_M:
            clean.append(pt)
    clean.append(chain[-1])
    return clean


# ── Parallel chain deduplication ─────────────────────────────────────────────

def remove_parallel_chains(chains, parallel_tol_m=2.0): #was 5.0
    """
    Within a single road, discard chains that are parallel duplicates of a
    longer chain. These arise because the SVG renders the same road geometry
    multiple times as slightly-offset overlapping paths.

    Algorithm:
      Sort chains longest-first. Keep the longest. For each subsequent chain,
      compute its average distance to every already-kept chain. If that
      average distance is below parallel_tol_m, it is a redundant parallel
      trace and is discarded.
    """
    if len(chains) <= 1:
        return chains

    def arc_m(c):
        return sum(dist_m(c[i], c[i + 1]) for i in range(len(c) - 1))

    def avg_dist_to_chain(candidate, reference):
        step = max(1, len(candidate) // 20)
        pts  = candidate[::step] + [candidate[-1]]
        dists = []
        for p in pts:
            min_d = float("inf")
            for i in range(len(reference) - 1):
                a, b = reference[i], reference[i + 1]
                dx, dy = b[0] - a[0], b[1] - a[1]
                lsq = dx * dx + dy * dy
                if lsq == 0:
                    cp = a
                else:
                    t  = max(0.0, min(1.0,
                             ((p[0]-a[0])*dx + (p[1]-a[1])*dy) / lsq))
                    cp = (a[0]+t*dx, a[1]+t*dy)
                min_d = min(min_d, dist_m(p, cp))
            dists.append(min_d)
        return sum(dists) / len(dists)

    sorted_chains = sorted(chains, key=arc_m, reverse=True)
    kept = [sorted_chains[0]]

    for candidate in sorted_chains[1:]:
        is_parallel = any(
            avg_dist_to_chain(candidate, ref) < parallel_tol_m
            for ref in kept
        )
        if not is_parallel:
            kept.append(candidate)

    return kept


# ── Intersection merging (Union-Find) ─────────────────────────────────────────

def merge_intersections(int_pts, radius_m):
    ids    = list(int_pts.keys())
    parent = {i: i for i in ids}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            if ra < rb: parent[rb] = ra
            else:       parent[ra] = rb

    if radius_m > 0:
        for i in range(len(ids)):
            for j in range(i + 1, len(ids)):
                if dist_m(int_pts[ids[i]], int_pts[ids[j]]) <= radius_m:
                    union(ids[i], ids[j])

    clusters = defaultdict(list)
    for iid in ids:
        clusters[find(iid)].append(iid)

    merged = {}
    for root, members in clusters.items():
        pts = [int_pts[m] for m in members]
        cx  = sum(p[0] for p in pts) / len(pts)
        cy  = sum(p[1] for p in pts) / len(pts)
        merged[root] = {
            "point"                  : [round(cx, 6), round(cy, 6)],
            "source_intersection_ids": sorted(members),
        }
    return merged


# ── Chain projection ──────────────────────────────────────────────────────────

def project_onto_chain(p, chain):
    """Return (arc_svg, snapped_point, dist_svg) for point p projected onto chain."""
    best_d, best_arc, best_pt = float("inf"), 0.0, chain[0]
    arc = 0.0
    for i in range(len(chain) - 1):
        a, b = chain[i], chain[i + 1]
        dx, dy = b[0] - a[0], b[1] - a[1]
        lsq = dx * dx + dy * dy
        if lsq == 0:
            t, cp = 0.0, a
        else:
            t = max(0.0, min(1.0,
                    ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / lsq))
            cp = lerp(a, b, t)
        d = dist_svg(p, cp)
        if d < best_d:
            best_d   = d
            best_arc = arc + t * math.sqrt(lsq)
            best_pt  = cp
        arc += math.sqrt(lsq)
    return best_arc, best_pt, best_d


def insert_into_chain(chain, arc_pos, pt):
    arc = 0.0
    for i in range(len(chain) - 1):
        seg = dist_svg(chain[i], chain[i + 1])
        if arc + seg >= arc_pos - 1e-9:
            return chain[:i + 1] + [pt] + chain[i + 1:]
        arc += seg
    return chain + [pt]


def sub_chain_svg(chain, arc_start, arc_end):
    """Extract the portion of chain between two SVG arc positions."""
    pts, arc, started = [], 0.0, False
    for i in range(len(chain) - 1):
        a, b    = chain[i], chain[i + 1]
        seg     = dist_svg(a, b)
        seg_end = arc + seg
        if not started and arc_start <= arc + 1e-9:
            t = (arc_start - arc) / seg if seg > 0 else 0
            pts.append(lerp(a, b, max(0.0, t)))
            started = True
        if started:
            if seg_end >= arc_end - 1e-9:
                t  = (arc_end - arc) / seg if seg > 0 else 1
                ep = lerp(a, b, min(1.0, t))
                if dist_svg(pts[-1], ep) > 1e-9:
                    pts.append(ep)
                break
            else:
                if dist_svg(pts[-1], b) > 1e-9:
                    pts.append(b)
        arc = seg_end
    if not pts and chain:
        pts = [chain[-1]]
    return pts


# ── Uniform-division sampler (NEW) ────────────────────────────────────────────

def n_divisions(arc_m):
    """
    Number of equal divisions for a segment of arc_m metres.
    n = ceil(arc_m / INTERVAL_M), guarded against floating-point overshoot.
    Minimum 1 (even a very short segment counts as 1 division).
    """
    raw     = arc_m / INTERVAL_M
    rounded = round(raw)
    if abs(raw - rounded) < 1e-6:
        return max(1, rounded)
    return max(1, math.ceil(raw))


def place_uniform_nodes(chain):
    """
    Divide chain into n_divisions(arc_length) equal parts and return the
    (n - 1) interior node positions as SVG (x, y) tuples.

    All gaps are identical: spacing = arc_length / n ≤ INTERVAL_M.
    Endpoints (chain[0] and chain[-1]) are NOT returned — they are the
    intersection / terminal nodes and are handled by the caller.

    Also returns the computed spacing_m for metadata.
    """
    total_m = chain_arc_m(chain)
    n       = n_divisions(total_m)
    spacing_m = total_m / n
    n_interior = n - 1

    if n_interior == 0:
        return [], spacing_m

    pts   = []
    acc_m = 0.0

    for i in range(len(chain) - 1):
        p1, p2 = chain[i], chain[i + 1]
        seg_m  = dist_m(p1, p2)
        if seg_m == 0:
            continue

        while len(pts) < n_interior:
            next_target_m = (len(pts) + 1) * spacing_m
            if next_target_m <= acc_m + seg_m + 1e-9:
                t = (next_target_m - acc_m) / seg_m
                pts.append(lerp(p1, p2, min(1.0, t)))
            else:
                break

        acc_m += seg_m
        if len(pts) >= n_interior:
            break

    return pts, spacing_m


def calculate_line_params(p1, p2):
    """
    Given two points p1 and p2, calculate the slope (m) and intercept (b) of the line.
    Returns the parameters for the line equation: y = mx + b
    """
    x1, y1 = p1
    x2, y2 = p2
    # Handling vertical lines to avoid division by zero
    if x2 == x1:
        m = float('inf')  # Vertical line
        b = x1  # x-intercept
    else:
        m = (y2 - y1) / (x2 - x1)
        b = y1 - m * x1
    return m, b

def solve_intersection(line1_params, line2_params):
    """
    Given the parameters of two lines, solve for their intersection point (if any).
    Returns the intersection point (x, y), or None if no valid intersection within the segments.
    """
    EPS = 1e-9

    m1, b1 = line1_params
    m2, b2 = line2_params
    
    # If both lines are vertical
    if m1 == float('inf') and m2 == float('inf'):
        return None  # Parallel vertical lines (no intersection)
    
    # If one line is vertical
    if m1 == float('inf'):
        x = b1
        y = m2 * x + b2
        return x, y
    
    if m2 == float('inf'):
        x = b2
        y = m1 * x + b1
        return x, y
    
    # Otherwise, solve for x where y1 = y2, i.e., m1*x + b1 = m2*x + b2
    if abs(m1 - m2) < EPS:
        return None # same line or no intersection
    else:
        x = (b2 - b1) / (m1 - m2)
        y = m1 * x + b1
        return x, y

def is_within_bounds(x, y, p1, p2, tolerance=1e-5):
    """
    Check if the intersection point (x, y) is within the bounds of the segment defined by p1 and p2.
    """
    x1, y1 = p1
    x2, y2 = p2
    # Check if the intersection point is within the bounds of the segment
    return min(x1, x2) - tolerance <= x <= max(x1, x2) + tolerance and \
           min(y1, y2) - tolerance <= y <= max(y1, y2) + tolerance

def remove_duplicates(intersections, tolerance):
    """
    Removes duplicate intersection points that are within the tolerance distance.
    Uses vectorized approach with NumPy.
    """
    length = len(intersections)
    if length == 0: return []
    elif length == 1: return intersections

    # Convert list of intersections to a numpy array for vectorized operations
    # print(intersections)    
    unique_points = []

    for point in intersections:
        if len(unique_points):
            distances = [np.linalg.norm(np.array(p[0]) - np.array(point[0])) for p in unique_points]
        else:
            distances = []

        min_dist, min_idx = None, None
        for idx, d in enumerate(distances):
            if d < tolerance and (min_dist is None or d < min_dist):
                min_dist = d
                min_idx = idx

        if min_idx is None:
            unique_points.append(list(point))  # now works
        else:
            unique_points[min_idx][1] = list(set(unique_points[min_idx][1] + point[1]))

    return np.array(unique_points, dtype=object)

def find_intersections(paths, tolerance=5e-2):
    """
    Find the intersections between all line segments in the given paths using linear equations.
    """

    intersections = []

    if len(paths) < 2:
        return intersections
    
    # Loop over all path pairs
    for i in range(len(paths)):
        for j in range(i + 1, len(paths)):
            path1 = paths[i]
            path2 = paths[j]
            
            # Iterate over all pairs of segments in path1 and path2
            for k in range(len(path1) - 1):
                for l in range(len(path2) - 1):
                    p1, p2 = path1[k], path1[k + 1]
                    p3, p4 = path2[l], path2[l + 1]
                    
                    # Calculate line parameters for each segment
                    line1_params = calculate_line_params(p1, p2)
                    line2_params = calculate_line_params(p3, p4)
                    
                    # Find the intersection of the two lines
                    intersection = solve_intersection(line1_params, line2_params)
                    
                    if intersection is not None:
                        x, y = intersection

                        # Check if the intersection is within the bounds of both segments
                        if is_within_bounds(x, y, p1, p2, tolerance) and is_within_bounds(x, y, p3, p4, tolerance):
                            # Add intersection to the list
                            intersections.append(((x, y), [i,j])) # note the intersecting paths

    return remove_duplicates(intersections, tolerance)

# ── Main ──────────────────────────────────────────────────────────────────────

def generate(input_path=INPUT_FILE, output_path=OUTPUT_FILE,
             merge_radius_m=MERGE_RADIUS_M):

    # Resolve input path relative to the script directory, not process CWD
    _ip = Path(input_path)
    inp = (_ip if _ip.is_absolute() else _CWD / _ip).resolve()
    if not inp.exists():
        raise FileNotFoundError(inp)

    with inp.open("rb") as f:
        raw_data = json.loads(f.read().decode("utf-8-sig"))

    road_data = raw_data.get("Road_ID", {})
    int_data  = raw_data.get("intersection_ID", {})
    raw_gateways = raw_data.get("gateway_points", [])

    gateways = {}
    if isinstance(raw_gateways, list):
        for item in raw_gateways:
            gid = item.get("id") if isinstance(item, dict) else None
            point = item.get("point") if isinstance(item, dict) else None
            if gid is None or not isinstance(point, list) or len(point) < 2:
                continue
            try:
                x = round(float(point[0]), 6)
                y = round(float(point[1]), 6)
            except (TypeError, ValueError):
                continue
            gateways[str(gid)] = {
                "point": [x, y]
            }

    # Step 0: merge nearby intersections
    print("Merging cross road intersections...")
    raw_int_pts = {iid: v["point"] for iid, v in int_data.items()}
    merged_ints = merge_intersections(raw_int_pts, merge_radius_m)
    n_raw, n_merged = len(raw_int_pts), len(merged_ints)

    print(f"\n{'='*65}")
    print(f"  Input          : {inp.name}")
    print(f"  Merge radius   : {merge_radius_m} m")
    print(f"  Intersections  : {n_raw} raw -> {n_merged} merged")
    print(f"  Interval       : {INTERVAL_M} m  (uniform division per segment)")
    print(f"  m/svg_x={M_PER_SVG_X:.3f}  m/svg_y={M_PER_SVG_Y:.3f}")
    print(f"  Roads          : {len(road_data)}")
    print(f"{'='*65}\n")

    # Step 1: parse, stitch, remove parallel duplicate chains, deduplicate vertices
    PARALLEL_TOL_M = 5.0   # chains within this avg distance are parallel duplicates
    road_chains = {}
    internal_ints = {}
    for rid, info in tqdm.tqdm(road_data.items(), 'Parsing and stiching roads'):
        parsed = parse_svg_path(info["path"])        
        raw_chains    = stitch(parsed, STITCH_TOL)
        unique_chains = remove_parallel_chains(raw_chains, PARALLEL_TOL_M)
        road_chains[rid] = [deduplicate_chain(c) for c in unique_chains]

        # print(road_chains[rid])
        
        internal_ints[rid] = {}
        iid_ctr = 0
        intersections = find_intersections(road_chains[rid], tolerance=4e-2) #TODO: change to meters and use correct scaling
        for iinter in intersections:
            iid_ctr += 1
            mid = f"int_{rid}_{iid_ctr}"           
            internal_ints[rid][mid] = iinter
            merged_ints[mid] = {
                "point": list(iinter[0]),
                "road_id": rid,                
                "source_intersection_ids": None,
                "is_internal": True,
            }
            

    # Step 2: snap each merged intersection onto its road chains
    int_on_road = {rid: {} for rid in road_chains}    
    for mid, minfo in tqdm.tqdm(merged_ints.items(), 'Snap merged intersections'):
        pt = tuple(minfo["point"])

        if minfo.get("is_internal"):
            continue

        for rid, chains in road_chains.items():
            best = None
            for ci, chain in enumerate(chains):
                arc, snapped, d = project_onto_chain(pt, chain)
                if d <= SNAP_TOL and (best is None or d < best[3]):
                    best = (ci, arc, snapped, d)
            if best is not None:
                ci, arc, snapped, _ = best
                int_on_road[rid][mid] = (ci, arc, snapped)

    # Step 3: split chains at intersections, sample each segment uniformly
    nodes   = {}
    nid_ctr = [0]

    def new_nid():
        nid_ctr[0] += 1
        return nid_ctr[0]

    int_nid = {}

    def get_or_create_int_node(mid):
        if mid not in int_nid:
            nid = new_nid()
            int_nid[mid] = nid
            minfo = merged_ints[mid]

            nodes[nid] = {
                "point": minfo["point"],
                "road_id": minfo.get("road_id"),  # internal keeps road_id
                "intersection_id": "is_internal" if minfo.get("is_internal") else mid,
                "source_intersection_ids": minfo.get("source_intersection_ids"),
                "neighbours": [],
                "is_internal": minfo.get("is_internal", False),
            }

        return int_nid[mid]

    seg_stats = []   # (arc_m, n, spacing_m) for reporting

    for rid, chains in tqdm.tqdm(road_chains.items(), 'Placing nodes on roads'):
        road_int_map = int_on_road[rid]
        internal_int_map = internal_ints[rid]

        # print(road_int_map)

        chain_ints   = defaultdict(list)
        for mid, (ci, arc, snapped) in road_int_map.items():
            chain_ints[ci].append((arc, mid, snapped))

        for mid, (pt, cidx) in internal_int_map.items():
            for ci in cidx:
                arc, snapped, _ = project_onto_chain(pt, chains[ci])
                chain_ints[ci].append((arc, mid, snapped))

        for ci, chain in enumerate(chains):
            ints_here = sorted(chain_ints[ci], key=lambda x: x[0])

            # print(f"rid: {rid}, ci: {ci}, ints_here: {len(ints_here)}")

            # Insert snapped intersection points into chain geometry
            working = list(chain)
            for arc, mid, snapped in ints_here:
                working = insert_into_chain(working, arc, snapped)

            # Re-project for accurate arc positions after insertion
            splits = []
            for _, mid, _ in ints_here: 
                arc, snapped, _ = project_onto_chain(
                    merged_ints[mid]["point"], working)
                splits.append((arc, mid, snapped))
            splits.sort(key=lambda x: x[0])

            total_arc   = sum(dist_svg(working[i], working[i + 1])
                              for i in range(len(working) - 1))
            breakpoints = ([(0.0,       None, working[0])] +
                           [(a, m, s) for a, m, s in splits] +
                           [(total_arc, None, working[-1])])
            seg_node_seqs = []

            # print(breakpoints)
            for k in range(len(breakpoints) - 1):
                arc_s, mid_s, snap_s = breakpoints[k]
                arc_e, mid_e, snap_e = breakpoints[k + 1]
                if arc_e - arc_s < 1e-9:
                    continue

                seg = sub_chain_svg(working, arc_s, arc_e)
                if not seg:
                    continue

                # Use snapped coords as exact segment endpoints
                if mid_s is not None:
                    seg[0]  = snap_s
                if mid_e is not None:
                    seg[-1] = snap_e

                has_int_start = (mid_s is not None)
                has_int_end   = (mid_e is not None)

                # ── NEW: uniform division sampling ────────────────────────────
                interior_pts, spacing_m = place_uniform_nodes(seg)
                arc_m = chain_arc_m(seg)
                n     = n_divisions(arc_m)
                seg_stats.append((arc_m, n, spacing_m))
                # ─────────────────────────────────────────────────────────────

                # Skip isolated short fragments with no intersections and no nodes
                if not interior_pts and not has_int_start and not has_int_end:
                    continue

                # Build node sequence
                seq = []
                if has_int_start:
                    seq.append(get_or_create_int_node(mid_s))
                for pt in interior_pts:
                    nid = new_nid()
                    nodes[nid] = {
                        "point"                  : [round(pt[0], 6), round(pt[1], 6)],
                        "road_id"                : rid,
                        "intersection_id"        : None,
                        "source_intersection_ids": None,
                        "neighbours"             : [],
                        "_spacing_m"             : round(spacing_m, 4),
                    }
                    seq.append(nid)
                if has_int_end:
                    seq.append(get_or_create_int_node(mid_e))

                if len(seq) >= 2:
                    seg_node_seqs.append(seq)

                # print(f"seg: {ci}, k: {k}, length (m): {arc_m}, nodes: {len(seq)}")

            # Wire neighbours
            for seq in seg_node_seqs:
                for si, nid in enumerate(seq):
                    if si > 0:
                        prev = seq[si - 1]
                        if prev not in nodes[nid]["neighbours"]:
                            nodes[nid]["neighbours"].append(prev)
                    if si < len(seq) - 1:
                        nxt = seq[si + 1]
                        if nxt not in nodes[nid]["neighbours"]:
                            nodes[nid]["neighbours"].append(nxt)
        
        # exit()

    # Step 4: post-process — remove cross-sequence spurious edges
    # An edge is spurious if its length is < 90% of the average target spacing
    # of its two endpoint nodes. This catches wiring artefacts while preserving
    # legitimate slightly-short edges caused by road curvature (which are ~95%+).
    RATIO_THRESHOLD = 0.90
    removed_edges = 0
    for nid, nd in tqdm.tqdm(list(nodes.items()), 'Post-process — remove cross-sequence spurious edges'):
        for nb_nid in list(nd["neighbours"]):
            nb = nodes.get(nb_nid)
            if nb is None:
                continue
            if nd["intersection_id"] or nb["intersection_id"]:
                continue
            d = dist_m(nd["point"], nb["point"])
            sp_a = nd.get("_spacing_m", INTERVAL_M)
            sp_b = nb.get("_spacing_m", INTERVAL_M)
            avg_sp = (sp_a + sp_b) / 2
            if d < avg_sp * RATIO_THRESHOLD:
                if nb_nid in nd["neighbours"]:
                    nd["neighbours"].remove(nb_nid)
                if nid in nb["neighbours"]:
                    nb["neighbours"].remove(nid)
                removed_edges += 1

    orphaned = [nid for nid, nd in nodes.items()
                if nd["intersection_id"] is None and len(nd["neighbours"]) == 0]
    for nid in orphaned:
        del nodes[nid]

    if removed_edges or orphaned:
        print(f"  Post-process: removed {removed_edges//2} spurious edges, "
              f"{len(orphaned)} orphaned nodes")

    # Step 5: write JSON output
    print("Writing output JSON....")
    out_nodes = {}
    for nid, nd in nodes.items():
        entry = {
            "point"                  : nd["point"],
            "road_id"                : nd["road_id"],
            "intersection_id"        : nd["intersection_id"],
            "source_intersection_ids": nd["source_intersection_ids"],
            "neighbours"             : [str(n) for n in nd["neighbours"]],
        }
        if "_spacing_m" in nd:
            entry["spacing_m"] = nd["_spacing_m"]
        out_nodes[str(nid)] = entry

    # Segment stats summary
    spacings = [s for _, _, s in seg_stats]
    import statistics as st
    sp_mean   = st.mean(spacings)   if spacings else 0
    sp_median = st.median(spacings) if spacings else 0
    sp_min    = min(spacings)       if spacings else 0
    sp_max    = max(spacings)       if spacings else 0

    output = {
        "metadata": {
            "input_file"            : inp.name,
            "merge_radius_m"        : merge_radius_m,
            "target_interval_m"     : INTERVAL_M,
            "algorithm"             : "uniform_division",
            "m_per_svg_x"           : round(M_PER_SVG_X, 6),
            "m_per_svg_y"           : round(M_PER_SVG_Y, 6),
            "intersections_raw"     : n_raw,
            "intersections_merged"  : n_merged,
            "total_nodes"           : len(out_nodes),
            "intersection_nodes"    : len(int_nid),
            "road_sample_nodes"     : len(out_nodes) - len(int_nid),
            "segment_spacing_stats" : {
                "mean_m"  : round(sp_mean,   4),
                "median_m": round(sp_median, 4),
                "min_m"   : round(sp_min,    4),
                "max_m"   : round(sp_max,    4),
                "n_segs"  : len(seg_stats),
            },
        },
        "nodes": out_nodes,
        "gateways": gateways,
    }

    # Resolve output path relative to the script directory, not process CWD
    _op = Path(output_path)
    out_path = (_op if _op.is_absolute() else _CWD / _op).resolve()
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(output, f, indent=2)

    print(f"  Total nodes    : {len(out_nodes)}")
    print(f"  Int nodes      : {len(int_nid)}  ({n_raw} raw -> {n_merged} merged)")
    print(f"  Road nodes     : {len(out_nodes) - len(int_nid)}")
    print(f"\n  Segment spacing stats ({len(seg_stats)} segments):")
    print(f"    mean={sp_mean:.4f}m  median={sp_median:.4f}m  "
          f"min={sp_min:.4f}m  max={sp_max:.4f}m")
    print(f"\n  Written -> {out_path}")
    print(f"\n{'='*65}  Done.\n")

    # Auto-generate validation SVG alongside the JSON (both in CWD)
    svg_path = Path(out_path).with_suffix('.svg')
    print("Generating validation SVG...")
    generate_svg(input_path=str(out_path), output_path=str(svg_path))


if __name__ == "__main__":
    generate()
