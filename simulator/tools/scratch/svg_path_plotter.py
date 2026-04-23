import math
import io
import webbrowser
from itertools import cycle
import numpy as np

def generate_svg(sections, points, width=500, height=500, padding_ratio=0.02):
    # Flatten all points to compute bounds
    all_points = [pt for section in sections for pt in section]
    
    min_x = min(p[0] for p in all_points)
    max_x = max(p[0] for p in all_points)
    min_y = min(p[1] for p in all_points)
    max_y = max(p[1] for p in all_points)

    # Compute width/height
    w = max_x - min_x
    h = max_y - min_y

    # Add padding
    pad_x = w * padding_ratio
    pad_y = h * padding_ratio

    view_x = min_x - pad_x
    view_y = min_y - pad_y
    view_w = w + 2 * pad_x
    view_h = h + 2 * pad_y

    # Color palette (cycles if more sections)
    colors = cycle([
        "red", "blue", "green", "orange", "purple",
        "brown", "pink", "cyan", "gold", "lime",
        "magenta", "indigo", "violet", "teal"
    ])

    # Stroke width relative to scale
    stroke_width = min(view_w, view_h) * 0.01

    svg_parts = []

    svg_parts.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'viewBox="{view_x} {view_y} {view_w} {view_h}" '
        f'width="{width}" height="{height}">'
    )

    svg_parts.append(f'<g fill="none" stroke-width="{stroke_width}">')

    for section in sections:
        if not section:
            continue
        
        color = next(colors)

        # Build path string
        d = "M " + " L ".join(f"{x},{y}" for x, y in section)

        svg_parts.append(f'<path d="{d}" stroke="{color}" />')

    dot_radius = 0.01
    for p in points:
        x, y = p
        color = next(colors)
        svg_parts.append(f'<circle cx="{x}" cy="{y}" r="{dot_radius}" fill="{color}" />')



    svg_parts.append('</g>')
    svg_parts.append('</svg>')

    return "\n".join(svg_parts)


def open_svg_in_browser(svg_content):
    # Create an in-memory file-like object from the SVG string
    svg_file = io.StringIO(svg_content)

    # Save content temporarily as a file and open it in the browser
    with open("temp_output.svg", "w") as f:
        f.write(svg_content)

    # Open the file in the default web browser
    webbrowser.open("temp_output.svg")


# ---- Example usage ----
if __name__ == "__main__":
    # sections = [[(329.289, 314.39), (329.096, 314.348), (329.17, 314.247), (329.243, 314.145), (329.319, 314.043), (329.394, 313.942), (329.468, 313.84), (329.543, 313.738), (329.613, 313.641), (329.635, 313.612), (329.633, 313.593), (329.5, 313.563), (329.472, 313.542), (329.463, 313.521), (329.495, 313.511), (329.508, 313.493), (329.542, 313.455), (329.552, 313.432), (329.557, 313.406), (329.574, 313.377), (329.591, 313.344), (329.573, 313.327), (329.581, 313.28), (329.592, 313.236), (329.597, 313.203), (329.602, 313.175), (329.602, 313.155), (329.598, 313.125)], [(329.101, 314.341), (329.044, 314.414), (328.966, 314.478)]]
    
    sections = [[(329.289, 314.39), (329.096, 314.348), (329.17, 314.247), (329.243, 314.145), (329.319, 314.043), (329.394, 313.942), (329.468, 313.84), (329.543, 313.738), (329.613, 313.641), (329.635, 313.612), (329.633, 313.593), (329.5, 313.563), (329.472, 313.542), (329.463, 313.521), (329.495, 313.511), (329.508, 313.493), (329.542, 313.455), (329.552, 313.432), (329.557, 313.406), (329.574, 313.377), (329.591, 313.344), (329.573, 313.327), (329.581, 313.28), (329.592, 313.236), (329.597, 313.203), (329.602, 313.175), (329.602, 313.155), (329.598, 313.125)], [(329.548, 313.627), (329.613, 313.641), (329.633, 313.593), (329.686, 313.542), (329.727, 313.484), (329.714, 313.464), (329.665, 313.452), (329.653, 313.435), (329.707, 313.359)], [(329.381, 
313.939), (329.739, 314.017)], [(329.455, 313.837), (329.813, 313.914)], [(329.53, 313.735), (329.867, 313.809)], [(329.613, 
313.641), (329.843, 313.685), (329.922, 313.703)], [(329.306, 314.04), (329.624, 314.11)], [(329.589, 313.521), (329.686, 313.542), (329.872, 313.573)], [(329.23, 314.142), (329.513, 314.203)], [(329.101, 314.341), (329.044, 314.414), (328.966, 314.478)], [(329.157, 314.244), (329.398, 314.296)], [(329.838, 313.693), (329.885, 313.629)], [(329.522, 313.369), (329.574, 313.377), (329.587, 313.379)]]
    
    # points = [(329.613, 313.641), (329.633, 313.593), (329.3941049943246, 313.9418552780931), (329.4681294601688, 313.8398239341704), (329.5430905754047, 313.7378744883678), (329.613, 313.641), (329.3190883108542, 314.0428810747164), (329.2431270371918, 314.1448295027162), (329.1701209035168, 314.24683106631903), (329.574, 313.377), (329.613, 313.641), (329.686, 313.542), (329.8437495764148, 313.68517078956285)]
    points = [(np.float64(329.61299999999994), np.float64(313.6410000000001)), (np.float64(329.633), np.float64(313.59299999999985)), (np.float64(329.39410712245285), np.float64(313.94185574176345)), (np.float64(329.4681279670251), np.float64(313.8398236130194)), (np.float64(329.5430920498948), np.float64(313.7378748121431)), (np.float64(329.613), np.float64(313.641)), (np.float64(329.3190885687042), np.float64(314.04288113147595)), (np.float64(329.2431226927579), np.float64(314.1448285662835)), (np.float64(329.09560189285924), np.float64(314.3479133652854)), (np.float64(329.1701233814609), np.float64(314.2468316009791)), (np.float64(329.56290517241376), np.float64(313.3752931034485)), (np.float64(329.61299999999994), np.float64(313.64099999999996)), (np.float64(329.6859999999999), np.float64(313.542)), (np.float64(329.8437672146772), np.float64(313.68514677150347))]
    
    svg = generate_svg(sections, points)

    # Open the SVG directly in the browser
    open_svg_in_browser(svg)

    print("SVG opened in browser.")