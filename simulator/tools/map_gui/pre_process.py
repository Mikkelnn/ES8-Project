import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
from shapely.geometry import Point, Polygon
import ipywidgets as widgets
from IPython.display import display, clear_output
import lonboard as lb
from shapely.ops import unary_union, linemerge
import pandas as pd
import networkx as nx
from shapely.geometry import LineString
from shapely.geometry import MultiLineString, Point
from shapely.geometry import MultiPoint
import math
import json
import re
import geopandas as gpd
from shapely.geometry import LineString, MultiLineString, Point, MultiPoint
from pathlib import Path
from urllib.request import urlretrieve
from zipfile import ZipFile
import os
import requests
import tqdm

LINE_TYPES  = (LineString, MultiLineString)
POINT_TYPES = (Point, MultiPoint)

def road_extractor(gdf, target_fclasses: list[str]):
    # Reproject everything to EPSG:4326 (WGS84) upfront for consistency.
    # lonboard also expects EPSG:4326, so this avoids downstream CRS issues.
    gdf = gdf.to_crs(epsg=4326)

    # Objective 1: Filter to only Secondary, Primary, Tertiary and residential roads    
    gdf_filtered = gdf[gdf["fclass"].isin(target_fclasses)].copy()

    gdf_filtered = gdf_filtered[gdf_filtered["name"].notna() & (gdf_filtered["name"] != "")]
    return gdf_filtered.reset_index(drop=True)


def extend_line(line, distance):
    """Extend a LineString by `distance` meters at both ends by extrapolating the end segments."""
    coords = list(line.coords)
    if len(coords) < 2:
        return line

    # Extend start: extrapolate backwards from coords[1] -> coords[0]
    x0, y0 = coords[0]
    x1, y1 = coords[1]
    dx, dy = x0 - x1, y0 - y1
    length = np.hypot(dx, dy)
    if length > 0:
        coords[0] = (x0 + distance * dx / length, y0 + distance * dy / length)

    # Extend end: extrapolate forwards from coords[-2] -> coords[-1]
    x0, y0 = coords[-2]
    x1, y1 = coords[-1]
    dx, dy = x1 - x0, y1 - y0
    length = np.hypot(dx, dy)
    if length > 0:
        coords[-1] = (x1 + distance * dx / length, y1 + distance * dy / length)

    return LineString(coords)


def merge_intersecting_segments(group):
    """
    Within a same-name group, build a graph where each segment is a node.
    Add an edge between two segments if they intersect or touch.
    Merge only the segments within each connected component.
    Returns a list of (row, merged_geometry) tuples — one per connected component.
    """
    geoms = list(group.geometry)
    n = len(geoms)

    G = nx.Graph()
    G.add_nodes_from(range(n))

    for i in range(n):
        for j in range(i + 1, n):
            if geoms[i].intersects(geoms[j]) or geoms[i].touches(geoms[j]):
                G.add_edge(i, j)

    rows = []
    for component in nx.connected_components(G):
        indices = list(component)
        merged_geom = unary_union([geoms[i] for i in indices])
        row = group.iloc[indices[0]].copy()
        row["geometry"] = merged_geom
        component_fclasses = group.iloc[indices]["fclass"].unique()
        row["fclass"] = ", ".join(sorted(component_fclasses))
        rows.append(row)

    return rows


def filtered_frame(gdf):
    # Drop rows with no name
    gdf = gdf[gdf["name"].notna() & (gdf["name"] != "")].copy()

    # Reproject to metric CRS (EPSG:3857) so 1 meter extension is accurate
    gdf_metric = gdf.to_crs(epsg=3857)

    # Explode MultiLineStrings into individual LineStrings
    gdf_exploded = gdf_metric.explode(index_parts=False).reset_index(drop=True)
    gdf_exploded = gdf_exploded[gdf_exploded.geometry.type == "LineString"].copy()

    # Extend each segment by x meter at both ends so near-touching segments overlap
    gdf_exploded["geometry"] = gdf_exploded.geometry.apply(lambda line: extend_line(line, 0.0))

    # For each name group, merge only connected (intersecting/touching) segments
    all_rows = []
    for name, group in tqdm.tqdm(gdf_exploded.groupby("name"), 'Merging intersecting segments'):
        all_rows.extend(merge_intersecting_segments(group))

    gdf_merged = gpd.GeoDataFrame(all_rows, geometry="geometry", crs="EPSG:3857").reset_index(drop=True)

    # Reproject back to WGS84
    return gdf_merged.to_crs(epsg=4326)


def find_road_intersections(gdf):
    """
    Find intersections between different roads in a GeoDataFrame.
    Uses a spatial index (STRtree) to avoid O(n²) pair comparisons.
    """
    gdf_metric = gdf.to_crs(epsg=3857).reset_index(drop=True)

    # Spatial index: only candidate pairs whose bounding boxes overlap are checked
    sindex = gdf_metric.sindex
    left_idx, right_idx = sindex.query(gdf_metric.geometry, predicate="intersects")

    # Keep unique pairs (i < j) — drops self-pairs and duplicates
    mask = left_idx < right_idx
    left_idx = left_idx[mask]
    right_idx = right_idx[mask]

    # Pre-filter pairs with the same road name
    names = gdf_metric.get("name", pd.Series([""] * len(gdf_metric))).fillna("").values
    name_mask = names[left_idx] != names[right_idx]
    left_idx = left_idx[name_mask]
    right_idx = right_idx[name_mask]

    geometries = gdf_metric.geometry.values
    intersection_points = []

    for i, j in tqdm.tqdm(zip(left_idx, right_idx), 'Intersection combinations', total=min(len(left_idx), len(right_idx))):
        geom_a = geometries[i]
        geom_b = geometries[j]

        intersection = geom_a.intersection(geom_b)
        if intersection.is_empty:
            continue

        pts = []
        if intersection.geom_type == "Point":
            pts = [intersection]
        elif intersection.geom_type == "MultiPoint":
            pts = list(intersection.geoms)
        elif intersection.geom_type in ("GeometryCollection", "MultiLineString", "LineString"):
            if hasattr(intersection, "geoms"):
                for g in intersection.geoms:
                    pts.append(g if g.geom_type == "Point" else g.centroid)
            else:
                pts.append(intersection.centroid)

        if not pts:
            continue

        road_a = gdf_metric.iloc[i]
        road_b = gdf_metric.iloc[j]
        name_a = road_a.get("name", road_a.get("osm_id", str(i)))
        name_b = road_b.get("name", road_b.get("osm_id", str(j)))
        fclass_a = road_a.get("fclass", "")
        fclass_b = road_b.get("fclass", "")
        osm_a = road_a.get("osm_id", "")
        osm_b = road_b.get("osm_id", "")

        for pt in pts:
            intersection_points.append({
                "geometry": pt,
                "road_a_name": name_a,
                "road_a_osm_id": osm_a,
                "road_a_fclass": fclass_a,
                "road_b_name": name_b,
                "road_b_osm_id": osm_b,
                "road_b_fclass": fclass_b,
                "intersecting_roads": f"{name_a} ({fclass_a}, osm_id={osm_a}) x {name_b} ({fclass_b}, osm_id={osm_b})"
            })

    if not intersection_points:
        print("No intersections found.")
        return gpd.GeoDataFrame(
            columns=["geometry", "road_a_name", "road_a_osm_id", "road_a_fclass",
                     "road_b_name", "road_b_osm_id", "road_b_fclass", "intersecting_roads"],
            geometry="geometry", crs="EPSG:3857"
        )

    print("Mapping to geopandas...")
    intersections_gdf = gpd.GeoDataFrame(intersection_points, geometry="geometry", crs="EPSG:3857")
    return intersections_gdf.to_crs(epsg=4326)

def cluster_nearby_intersections(intersections_gdf, radius_m=10):
    """
    Cluster intersection points within `radius_m` meters of each other.
    Merges nearby points into a single centroid, combining road info from all.
    """
    gdf = intersections_gdf.to_crs(epsg=3857).copy().reset_index(drop=True)
    
    # Buffer each point by radius_m/2 so overlapping buffers indicate proximity
    buffered = gdf.geometry.buffer(radius_m / 2)
    
    # Build union clusters using spatial index
    sindex = buffered.sindex
    visited = set()
    clusters = []

    for i in tqdm.tqdm(range(len(gdf)), "Initializing clusters"):
        if i in visited:
            continue
        # Find all points whose buffers intersect with point i's buffer
        candidates = list(sindex.query(buffered.iloc[i], predicate="intersects"))
        cluster = [c for c in candidates if c not in visited]
        for c in cluster:
            visited.add(c)
        clusters.append(cluster)

    merged_rows = []
    for cluster in tqdm.tqdm(clusters, "Processing clusters"):
        rows = gdf.iloc[cluster]
        # Centroid of all points in the cluster
        centroid = unary_union(rows.geometry).centroid

        # Collect all unique roads involved
        roads_a = set(zip(rows["road_a_name"], rows["road_a_osm_id"], rows["road_a_fclass"]))
        roads_b = set(zip(rows["road_b_name"], rows["road_b_osm_id"], rows["road_b_fclass"]))
        all_roads = roads_a | roads_b

        road_strs = [f"{name} ({fclass}, osm_id={osm_id})" for name, osm_id, fclass in sorted(all_roads)]
        intersecting_roads_str = " x ".join(road_strs)

        road_list = sorted(all_roads)
        merged_rows.append({
            "geometry": centroid,
            "road_a_name": road_list[0][0] if len(road_list) > 0 else "",
            "road_a_osm_id": road_list[0][1] if len(road_list) > 0 else "",
            "road_a_fclass": road_list[0][2] if len(road_list) > 0 else "",
            "road_b_name": road_list[1][0] if len(road_list) > 1 else "",
            "road_b_osm_id": road_list[1][1] if len(road_list) > 1 else "",
            "road_b_fclass": road_list[1][2] if len(road_list) > 1 else "",
            "intersecting_roads": intersecting_roads_str,
            "num_roads": len(all_roads),
            "cluster_size": len(cluster),
        })

    print("Mapping to geopandas...")
    result = gpd.GeoDataFrame(merged_rows, geometry="geometry", crs="EPSG:3857")
    result = result.to_crs(epsg=4326)
    return result

def combine_road_intersections(roadnetwork_filtered: gpd.GeoDataFrame, clustered_intersections: gpd.GeoDataFrame = None):
    combined = []
    
    if "intersection_id" not in clustered_intersections.columns:
        clustered_intersections["intersection_id"] = clustered_intersections.index


    if clustered_intersections is not None:
        clustered_intersections = clustered_intersections.copy()

        # Ensure intersections have an "id" field used later by gdf_to_road_intersection_json.
        #if "id" not in clustered_intersections.columns:
        #    if "intersection_id" in clustered_intersections.columns:
        #        clustered_intersections["id"] = clustered_intersections["intersection_id"]
        #    else:
        #        clustered_intersections["id"] = clustered_intersections.index
    
        # Convert intersections_clustered to GeoJSON features
        intersections_geojson = json.loads(clustered_intersections.to_json())

        # Tag intersection features with a type indicator
        for feature in intersections_geojson['features']:
            feature['properties']['feature_type'] = 'intersection'
            feature['properties']['id'] = feature['properties'].get('intersection_id')
            feature['id'] = feature['properties']['id']

        combined = intersections_geojson['features']

    if roadnetwork_filtered is not None:
        # Convert intersections_clustered to GeoJSON features
        roadnetwork_geojson = json.loads(roadnetwork_filtered.to_json())

        # Tag road features with a type indicator
        for feature in roadnetwork_geojson['features']:
            feature['properties']['feature_type'] = 'road'
            feature['properties']['id'] = None
            feature['id'] = None

        combined = roadnetwork_geojson['features'] + combined

    # Combine features
    combined_geojson = {
        "type": "FeatureCollection",
        "features": combined
    }

    combined_gdf = gpd.GeoDataFrame.from_features(combined_geojson["features"], crs="EPSG:4326")
    return combined_gdf
    # return combined_geojson

# =========================================================================== #
#  Internal helpers                                                           #
# =========================================================================== #

def _is_null(value) -> bool:
    """Return True for None, empty string, or float NaN."""
    if value is None or value == "":
        return True
    try:
        return math.isnan(float(value))
    except (TypeError, ValueError):
        return False


def _build_projector(gdf: gpd.GeoDataFrame,
                     svg_w: float = 1200,
                     svg_h: float = 900,
                     padding: float = 40.0):
    """
    Return a (lon, lat) -> (svg_x, svg_y) projection function derived from
    the bounding box of the entire GeoDataFrame.

    - Y-axis is flipped  (SVG origin = top-left)
    - Aspect ratio is preserved via uniform scaling
    - The map is centred inside the viewport with the requested padding
    """
    if gdf is None or gdf.empty or "geometry" not in gdf.columns:
        raise ValueError("Cannot build projector: input GeoDataFrame has no geometry rows.")

    non_empty_geoms = gdf.geometry.dropna()
    if non_empty_geoms.empty:
        raise ValueError("Cannot build projector: all geometry values are null.")

    min_x, min_y, max_x, max_y = non_empty_geoms.total_bounds
    if any(math.isnan(v) for v in (min_x, min_y, max_x, max_y)):
        raise ValueError("Cannot build projector: geometry bounds are invalid (NaN).")

    # print(f"GeoDataFrame bounds: min_x={min_x}, min_y={min_y}, max_x={max_x}, max_y={max_y}")

    usable_w = svg_w - 2 * padding
    usable_h = svg_h - 2 * padding
    span_x   = max_x - min_x or 1e-9
    span_y   = max_y - min_y or 1e-9
    scale    = min(usable_w / span_x, usable_h / span_y)

    offset_x = padding + (usable_w - span_x * scale) / 2
    offset_y = padding + (usable_h - span_y * scale) / 2

    def project(lon: float, lat: float) -> tuple:
        x = round(offset_x + (lon - min_x) * scale, 3)
        y = round(offset_y + (max_y - lat) * scale, 3)   # flip Y
        return x, y
    
    #Change: Added metadata to aid the scaling calculation in the JS GUI
    metadata = {
        "scale": scale,
        "bounds": {
            "min_x": min_x,
            "min_y": min_y,
            "max_x": max_x,
            "max_y": max_y
        },
        "svg_dimensions": {
            "width": svg_w,
            "height": svg_h,
            "used_width": usable_w,
            "used_height": usable_h,
            "padding": padding
        },
        "offset": {
            "x": offset_x,
            "y": offset_y
        }
    }

    return project, metadata


def _linestring_to_svg_path(coords, project) -> str:
    """
    Convert a coordinate sequence to an SVG path 'd' string.
    e.g. "M10,20 L30,40 L50,60"
    """
    parts = []
    for i, (lon, lat) in enumerate(coords):
        x, y = project(lon, lat)
        parts.append(f"{'M' if i == 0 else 'L'}{x},{y}")
    return " ".join(parts)


def _geom_to_path_details(geom, project) -> list:
    """
    Return a list of SVG path 'd' strings for a LineString or MultiLineString.
    Each sub-linestring in a MultiLineString becomes its own entry.
    """
    if isinstance(geom, LineString):
        return [_linestring_to_svg_path(geom.coords, project)]
    if isinstance(geom, MultiLineString):
        return [_linestring_to_svg_path(line.coords, project)
                for line in geom.geoms]
    return []


def _geom_to_point(geom, project) -> list:
    """
    Return a list of {"cx": x, "cy": y} dicts for a Point or MultiPoint.
    """
    if isinstance(geom, Point):
        cx, cy = project(geom.x, geom.y)
        return [{"cx": cx, "cy": cy}]
    if isinstance(geom, MultiPoint):
        return [{"cx": project(pt.x, pt.y)[0], "cy": project(pt.x, pt.y)[1]}
                for pt in geom.geoms]
    return []


# =========================================================================== #
#  Main export function                                                       #
# =========================================================================== #

def gdf_to_road_intersection_json(gdf: gpd.GeoDataFrame, svg_width: int = 1200, svg_height: int= 900, padding: float = 40.0) -> dict:
    """
    Build a roads <-> intersections mapping with embedded SVG geometry
    and write it as a single JSON file.

    Geometry-aware column mapping
    ─────────────────────────────
    LineString / MultiLineString  ->  Road_ID entry
        'osm_id'        used as the key
        'path_details'  list of SVG path 'd' strings (one per sub-linestring)

    Point / MultiPoint            ->  intersection_ID entry
        'id'            used as the key
        'road_a_osm_id' / 'road_b_osm_id'  -> road_IDs list
        'point'         list of {"cx": x, "cy": y} SVG coordinates

    Output schema
    ─────────────
    {
      "Road_ID": {
        "<osm_id>": {
          "intersection_IDs": ["<id>", ...],
          "path_details":     ["M x,y L x,y ...", ...]
        }
      },
      "intersection_ID": {
        "<id>": {
          "road_IDs": ["<osm_id_a>", "<osm_id_b>"],
          "point":    [{"cx": x, "cy": y}]
        }
      }
    }

    Parameters
    ──────────
    gdf         : Input GeoDataFrame (geographic CRS recommended).
    output_path : Destination JSON file path.
    svg_width   : Viewport width  used to compute SVG coordinates (default 1200).
    svg_height  : Viewport height used to compute SVG coordinates (default 900).
    padding     : Margin (px) around the map inside the viewport  (default 40).
    """

    project, metadata = _build_projector(gdf, svg_width, svg_height, padding)

    road_section:         dict = {}
    intersection_section: dict = {}

    for _, row in gdf.iterrows():
        geom = row.get("geometry")
        if geom is None:
            continue

        # ── Roads (LineString / MultiLineString) ───────────────────────────── #
        if isinstance(geom, LINE_TYPES):
            osm_id = str(row["osm_id"])
            if osm_id not in road_section:
                road_section[osm_id] = {
                    "intersection_IDs": [],
                    "path":     _geom_to_path_details(geom, project),
                }

        # ── Intersections (Point / MultiPoint) ────────────────────────────── #
        elif isinstance(geom, POINT_TYPES):
            int_id = str(row["id"])

            road_osm_ids = (
                ([str(row["road_a_osm_id"])] if not _is_null(row.get("road_a_osm_id")) else []) +
                ([str(row["road_b_osm_id"])] if not _is_null(row.get("road_b_osm_id")) else [])
            )

            intersection_section[int_id] = {
                "road_IDs": road_osm_ids,
                "point":    _geom_to_point(geom, project),
            }

            # Back-fill each road's intersection_IDs list
            for osm_id in road_osm_ids:
                if osm_id not in road_section:
                    road_section[osm_id] = {"intersection_IDs": [], "path": []}
                if int_id not in road_section[osm_id]["intersection_IDs"]:
                    road_section[osm_id]["intersection_IDs"].append(int_id)

    #Change added metadata to the result dict to aid the scaling calculation in the JS GUI
    result = {
        "metadata": metadata,
        "Road_ID":         road_section,
        "intersection_ID": intersection_section,
    }

    return result


def result_to_js(result: dict,
                output_path: str = "processedRoads_test.js",
                variable_name: str = "RAW") -> dict:
    """
    Convert the generated result dict into processedRoads.js format for the HTML GUI.
    Exports: roads (SVG paths), intersections (coordinates), and roads_bb (bounding boxes).
    
    Output format:
    const RAW = {
        "metadata": {...scale, bounds, etc...},
        "roads": {"<osm_id>": "M x,y L x,y ..."},
        "intersections": {"<int_id>": [cx, cy]},
        "roads_bb": {"<osm_id>": [x1, y1, x2, y2]}
    };
    """
    metadata_in = result.get("metadata", {}) if isinstance(result, dict) else {}
    roads_in = result.get("Road_ID", {}) if isinstance(result, dict) else {}
    intersections_in = result.get("intersection_ID", {}) if isinstance(result, dict) else {}
    
    roads_out = {}
    intersections_out = {}
    roads_bb_out = {}

    # Process roads and calculate bounding boxes
    for osm_id, road_info in roads_in.items():
        if not isinstance(road_info, dict):
            continue

        # Each road may contain multiple path fragments; join them into one string
        path_parts = road_info.get("path", [])
        if isinstance(path_parts, list):
            joined_path = " ".join(p for p in path_parts if isinstance(p, str) and p.strip())
        elif isinstance(path_parts, str):
            joined_path = path_parts
        else:
            joined_path = ""

        if joined_path:
            roads_out[str(osm_id)] = joined_path
            
            # Calculate bounding box from SVG path commands (M x,y L x,y ...)
            coords = []
            for match in re.finditer(r'([ML])\s*([\d.]+)[,\s]+([\d.]+)', joined_path):
                coords.append((float(match.group(2)), float(match.group(3))))
            
            if coords:
                xs = [c[0] for c in coords]
                ys = [c[1] for c in coords]
                roads_bb_out[str(osm_id)] = [min(xs), min(ys), max(xs), max(ys)]

    # Process intersections
    for int_id, int_info in intersections_in.items():
        if not isinstance(int_info, dict):
            continue
        
        point_data = int_info.get("point", [])
        if isinstance(point_data, list) and len(point_data) > 0:
            # Extract first point [cx, cy]
            first_point = point_data[0]
            if isinstance(first_point, dict):
                cx = first_point.get("cx")
                cy = first_point.get("cy")
                if cx is not None and cy is not None:
                    intersections_out[str(int_id)] = [cx, cy]

    payload = {
        "metadata": metadata_in,
        "roads": roads_out,
        "intersections": intersections_out,
        "roads_bb": roads_bb_out
    }

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(f"const {variable_name} = ")
        json.dump(payload, f, separators=(",", ":"), ensure_ascii=False)
        f.write(";\n")
    return payload



def download_and_extract(url: str, filename: str):
    def _download(url: str, filename: str):
      with open(filename, 'wb') as f:
          with requests.get(url, stream=True) as r:
              r.raise_for_status()
              total = int(r.headers.get('content-length', 0))

              # tqdm has many interesting parameters. Feel free to experiment!
              tqdm_params = {
                  'desc': url,
                  'total': total,
                  'miniters': 1,
                  'unit': 'B',
                  'unit_scale': True,
                  'unit_divisor': 1024,
              }
              with tqdm.tqdm(**tqdm_params) as pb:
                  for chunk in r.iter_content(chunk_size=8192):
                      pb.update(len(chunk))
                      f.write(chunk)

    try:
        print("Downloading data...")

        download_name = url.split('/')[-1]
        # urlretrieve(url, download_name)
        _download(url, download_name)

        print(f"Successfully downloaded {download_name}, extracting...")

        # loading the temp.zip and creating a zip object
        with ZipFile(download_name, 'r') as zObject:
          # Extracting specific file in the zip
          # into a specific location.
          zObject.extract(filename)
        zObject.close()

        os.remove(download_name)

    except Exception as e:
        print(f"An error occurred: {e}, Please download and extract manually: {url}")
   

if __name__ == "__main__":
        geo_data_file = "denmark.gpkg"
        url = "https://download.geofabrik.de/europe/denmark-latest-free.gpkg.zip"

        layer_name = "gis_osm_roads_free"
        target_classes = ["secondary", "primary", "tertiary", "residential", "unclassified"]
        
        result_name = "processedRoads.js"

        if not Path(geo_data_file).exists():
                download_and_extract(url, geo_data_file)

        # load road layer, extract and filter
        print(f"Loading data ({geo_data_file})...")
        gdf = gpd.read_file(geo_data_file, layer=layer_name)

        print("Extract classes...")
        gdf_classes = road_extractor(gdf, target_fclasses=target_classes)

        print("Filter frame...")
        roadnetwork_filtered = filtered_frame(gdf_classes)

        print("Find and cluster intersections...")
        intersections = find_road_intersections(roadnetwork_filtered)
        intesection_clustered = cluster_nearby_intersections(intersections)
        # intesection_clustered = None

        print("Combining roads and intersection data...")
        combined_gdf = combine_road_intersections(roadnetwork_filtered, intesection_clustered)

        # build data format
        print("Converting combined data to json format used in GUI...")
        result = gdf_to_road_intersection_json(combined_gdf)

        # save data
        result_to_js(result, output_path=result_name)
        print(f"JSON written to: {result_name}")
