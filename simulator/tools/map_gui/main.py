import folium
import geopandas as gpd
import sys
import os


def load_geojson(filepath: str) -> gpd.GeoDataFrame:
    """Load a GeoJSON file into a GeoDataFrame."""
    if not os.path.exists(filepath):
        print(f"[ERROR] File not found: {filepath}")
        sys.exit(1)
    gdf = gpd.read_file(filepath)
    print(f"[INFO] Loaded {len(gdf)} features from '{filepath}'")
    print(f"[INFO] Columns: {list(gdf.columns)}")
    print(f"[INFO] CRS: {gdf.crs}")
    return gdf


def filter_roads(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """
    Filter road features from the GeoDataFrame based on 'fclass' column.
    Falls back to all LineString geometries if 'fclass' is not found.
    """
    # --- Try fclass column (infrastructure datasets) ---
    if "fclass" in gdf.columns:
        roads = gdf[gdf["fclass"].notna()].copy()
        print(f"[INFO] Filtered {len(roads)} road features using 'fclass' column.")
        return roads

    # --- Fallback: use all LineString geometries ---
    roads = gdf[gdf.geometry.geom_type == "LineString"].copy()
    print(f"[INFO] No 'fclass' column found. Using all {len(roads)} LineString features.")
    return roads


def build_map(roads: gpd.GeoDataFrame, output_html: str = "roads_map.html") -> None:
    """Build and save an interactive Folium map of the road network."""

    if roads.empty:
        print("[WARNING] No road features to display.")
        return

    # Compute map center from bounds (avoids CRS warning)
    bounds = roads.total_bounds  # [minx, miny, maxx, maxy]
    center_lon = (bounds[0] + bounds[2]) / 2
    center_lat = (bounds[1] + bounds[3]) / 2

    m = folium.Map(location=[center_lat, center_lon], zoom_start=13, control_scale=True)

    # Add a tile layer switcher
    folium.TileLayer("OpenStreetMap", name="OpenStreetMap").add_to(m)
    folium.TileLayer("CartoDB positron", name="CartoDB Positron").add_to(m)

    # Style function for road lines
    def road_style(feature):
        return {
            "color": "#1a73e8",
            "weight": 3,
            "opacity": 0.8,
        }

    def road_highlight(feature):
        return {
            "color": "#e84a1a",
            "weight": 5,
            "opacity": 1.0,
        }

    # Add all roads as a single GeoJSON layer
    folium.GeoJson(
        data=roads,
        name="Roads",
        style_function=road_style,
        highlight_function=road_highlight,
        tooltip=folium.GeoJsonTooltip(fields=['name'], aliases=['Road:'], sticky=True),
        popup=folium.GeoJsonPopup(
            fields=['name', 'fclass'],
            aliases=['Name:', 'Class:'],
            max_width=250
        ),
    ).add_to(m)

    # Layer control
    folium.LayerControl().add_to(m)

    m.save(output_html)
    print(f"[INFO] Interactive map saved to '{output_html}'")
    print("[INFO] Open it in a browser to explore the road network.")


# ── Entry point ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    # Build path relative to this script's location
    SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
    GEOJSON_PATH = os.path.join(SCRIPT_DIR, "..", "..", "GIS_data", "GIS_mainroad_data", "wgs84_geojson", "infrastruktur_secondary.geojson")
    GEOJSON_PATH = os.path.normpath(GEOJSON_PATH)
    OUTPUT_HTML  = "roads_map.html"

    gdf   = load_geojson(GEOJSON_PATH)
    roads = filter_roads(gdf)
    build_map(roads, output_html=OUTPUT_HTML)