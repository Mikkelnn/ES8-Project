"""Convert longitude/latitude coordinates into SVG coordinates.

The projection matches the reference implementation used in the notebook:

    - the projection is derived from a fixed road-network bounding box
    - the Y axis is flipped so SVG origin stays at the top-left
    - scaling is uniform so aspect ratio is preserved
    - the projected map is centered inside the padded viewport

The road network extent is fixed, so the script does not need to read the
GeoJSON file at runtime.

Example
-------
    python svg_point_calculator.py 12.34 56.78
"""

from __future__ import annotations

import argparse
from typing import Callable

DEFAULT_BOUNDS = (8.084347, 54.5737391, 15.1519023, 57.7382542)


def _build_projector(
	min_x: float,
	min_y: float,
	max_x: float,
	max_y: float,
	svg_w: float = 1200,
	svg_h: float = 900,
	padding: float = 40.0,
) -> Callable[[float, float], tuple[float, float]]:
	"""Return a (lon, lat) -> (svg_x, svg_y) projection function."""

	usable_w = svg_w - 2 * padding
	usable_h = svg_h - 2 * padding
	span_x = max_x - min_x or 1e-9
	span_y = max_y - min_y or 1e-9
	scale = min(usable_w / span_x, usable_h / span_y)

	offset_x = padding + (usable_w - span_x * scale) / 2
	offset_y = padding + (usable_h - span_y * scale) / 2

	def project(lon: float, lat: float) -> tuple[float, float]:
		x = round(offset_x + (lon - min_x) * scale, 3)
		y = round(offset_y + (max_y - lat) * scale, 3)
		return x, y

	return project


def build_projector(
	svg_w: float = 1200,
	svg_h: float = 900,
	padding: float = 40.0,
) -> Callable[[float, float], tuple[float, float]]:
	"""Build a projector using the fixed road-network bounds."""

	min_lon, min_lat, max_lon, max_lat = DEFAULT_BOUNDS
	return _build_projector(
		min_lon,
		min_lat,
		max_lon,
		max_lat,
		svg_w=svg_w,
		svg_h=svg_h,
		padding=padding,
	)


def lon_lat_to_svg(
	lon: float,
	lat: float,
	svg_w: float = 1200,
	svg_h: float = 900,
	padding: float = 40.0,
) -> tuple[float, float]:
	"""Convert one longitude/latitude pair into SVG coordinates."""

	projector = build_projector(svg_w=svg_w, svg_h=svg_h, padding=padding)
	return projector(lon, lat)


def parse_args() -> argparse.Namespace:
	parser = argparse.ArgumentParser(description="Project a longitude/latitude pair into SVG coordinates.")
	parser.add_argument("lon", type=float, help="Longitude value to project")
	parser.add_argument("lat", type=float, help="Latitude value to project")
	parser.add_argument("--svg-w", type=float, default=1200.0, help="SVG canvas width")
	parser.add_argument("--svg-h", type=float, default=900.0, help="SVG canvas height")
	parser.add_argument("--padding", type=float, default=40.0, help="Padding inside the canvas")
	return parser.parse_args()


def main() -> None:
	args = parse_args()

	projector = build_projector(svg_w=args.svg_w, svg_h=args.svg_h, padding=args.padding)

	x, y = projector(args.lon, args.lat)
	print(f"svg_x={x}, svg_y={y}")


if __name__ == "__main__":
	main()
