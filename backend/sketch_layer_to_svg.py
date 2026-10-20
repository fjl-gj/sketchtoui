from __future__ import annotations

import argparse
import html
import json
from pathlib import Path
from typing import Any


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as source:
        return json.load(source)


def find_layer(layer: dict[str, Any], layer_id: str, ancestors: list[dict[str, Any]] | None = None) -> tuple[dict[str, Any], list[dict[str, Any]]] | None:
    current_ancestors = ancestors or []
    if layer.get("do_objectID") == layer_id:
        return layer, current_ancestors
    for child in layer.get("layers", []):
        result = find_layer(child, layer_id, [*current_ancestors, layer])
        if result is not None:
            return result
    return None


def find_page_layer(sketch_dir: Path, page_id: str, layer_id: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    page_path = sketch_dir / "pages" / f"{page_id}.json"
    page = load_json(page_path)
    result = find_layer(page, layer_id)
    if result is None:
        raise ValueError(f"Layer {layer_id} was not found in {page_path}.")
    return result


def parse_point(value: str) -> tuple[float, float]:
    stripped = value.strip().removeprefix("{").removesuffix("}")
    x, y = stripped.split(",", maxsplit=1)
    return float(x), float(y)


def point_at(value: str, frame: dict[str, Any], offset_x: float, offset_y: float) -> tuple[float, float]:
    x, y = parse_point(value)
    return offset_x + x * float(frame.get("width", 0)), offset_y + y * float(frame.get("height", 0))


def number(value: float) -> str:
    return f"{value:.6f}".rstrip("0").rstrip(".") or "0"


def shape_path_data(layer: dict[str, Any], offset_x: float, offset_y: float) -> str:
    points = layer.get("points", [])
    if len(points) < 2:
        return ""
    frame = layer.get("frame", {})
    start_x, start_y = point_at(points[0]["point"], frame, offset_x, offset_y)
    commands = [f"M {number(start_x)} {number(start_y)}"]
    for index in range(1, len(points)):
        previous = points[index - 1]
        current = points[index]
        end_x, end_y = point_at(current["point"], frame, offset_x, offset_y)
        has_curve = previous.get("hasCurveTo", False) or current.get("hasCurveFrom", False)
        if not has_curve:
            commands.append(f"L {number(end_x)} {number(end_y)}")
            continue
        control_one_x, control_one_y = point_at(previous.get("curveFrom", previous["point"]), frame, offset_x, offset_y)
        control_two_x, control_two_y = point_at(current.get("curveTo", current["point"]), frame, offset_x, offset_y)
        commands.append(f"C {number(control_one_x)} {number(control_one_y)} {number(control_two_x)} {number(control_two_y)} {number(end_x)} {number(end_y)}")

    previous = points[-1]
    current = points[0]
    has_curve = previous.get("hasCurveTo", False) or current.get("hasCurveFrom", False)
    if has_curve:
        control_one_x, control_one_y = point_at(previous.get("curveFrom", previous["point"]), frame, offset_x, offset_y)
        control_two_x, control_two_y = point_at(current.get("curveTo", current["point"]), frame, offset_x, offset_y)
        commands.append(f"C {number(control_one_x)} {number(control_one_y)} {number(control_two_x)} {number(control_two_y)} {number(start_x)} {number(start_y)}")
    commands.append("Z")
    return " ".join(commands)


def color_value(fill: dict[str, Any] | None) -> str | None:
    if not fill:
        return None
    color = fill.get("color") or {}
    if not color:
        return None
    red = round(float(color.get("red", 0)) * 255)
    green = round(float(color.get("green", 0)) * 255)
    blue = round(float(color.get("blue", 0)) * 255)
    alpha = float(color.get("alpha", 1)) * float((fill.get("contextSettings") or {}).get("opacity", 1))
    if alpha >= 0.999:
        return f"#{red:02X}{green:02X}{blue:02X}"
    return f"rgba({red}, {green}, {blue}, {alpha:.4f})"


def enabled_fill(layer: dict[str, Any]) -> str | None:
    for fill in (layer.get("style") or {}).get("fills", []):
        if fill.get("isEnabled", True) and fill.get("fillType", 0) == 0:
            return color_value(fill)
    return None


def style_opacity(layer: dict[str, Any]) -> float:
    return float(((layer.get("style") or {}).get("contextSettings") or {}).get("opacity", 1))


def group_fill_rule(layer: dict[str, Any], path_count: int) -> str:
    if path_count <= 1:
        return "nonzero"
    return "evenodd" if (layer.get("style") or {}).get("windingRule", 0) == 0 else "nonzero"


def render_layer(layer: dict[str, Any], inherited_fill: str | None = None, inherited_opacity: float = 1, offset_x: float = 0, offset_y: float = 0) -> str:
    if not layer.get("isVisible", True):
        return ""
    own_fill = enabled_fill(layer)
    fill = own_fill or inherited_fill
    opacity = inherited_opacity * style_opacity(layer)
    layer_class = layer.get("_class")
    frame = layer.get("frame") or {}

    if layer_class == "shapePath":
        path_data = shape_path_data(layer, offset_x + float(frame.get("x", 0)), offset_y + float(frame.get("y", 0)))
        if not path_data or not fill:
            return ""
        return f'<path d="{path_data}" fill="{fill}" fill-opacity="{number(opacity)}" fill-rule="nonzero" />'

    children = layer.get("layers", [])
    if not children:
        return ""
    child_offset_x = offset_x + float(frame.get("x", 0))
    child_offset_y = offset_y + float(frame.get("y", 0))
    direct_paths = [child for child in children if child.get("_class") == "shapePath" and child.get("isVisible", True)]
    nested_layers = [child for child in children if child.get("_class") != "shapePath"]
    fragments: list[str] = []
    if direct_paths and fill:
        path_data = " ".join(
            shape_path_data(child, child_offset_x + float((child.get("frame") or {}).get("x", 0)), child_offset_y + float((child.get("frame") or {}).get("y", 0)))
            for child in direct_paths
        ).strip()
        if path_data:
            fragments.append(f'<path d="{path_data}" fill="{fill}" fill-opacity="{number(opacity)}" fill-rule="{group_fill_rule(layer, len(direct_paths))}" />')
    for child in nested_layers:
        fragments.append(render_layer(child, fill, opacity, child_offset_x, child_offset_y))
    return "".join(fragment for fragment in fragments if fragment)


def nearest_painted_shape_group(target: dict[str, Any], ancestors: list[dict[str, Any]]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    chain = [*ancestors, target]
    for index in range(len(chain) - 1, -1, -1):
        candidate = chain[index]
        if candidate.get("_class") == "shapeGroup" and enabled_fill(candidate):
            return candidate, chain[:index]
    return target, ancestors


def export_svg(sketch_dir: Path, page_id: str, layer_id: str, output_path: Path) -> Path:
    target, ancestors = find_page_layer(sketch_dir, page_id, layer_id)
    root, root_ancestors = nearest_painted_shape_group(target, ancestors)
    frame = root.get("frame") or {}
    width = float(frame.get("width", 0))
    height = float(frame.get("height", 0))
    if width <= 0 or height <= 0:
        raise ValueError("The selected SVG root has an empty frame.")
    content = render_layer(root)
    if not content:
        raise ValueError("The selected layer does not have a renderable solid fill path.")
    title = html.escape(str(root.get("name") or layer_id))
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{number(width)}" height="{number(height)}" viewBox="0 0 {number(width)} {number(height)}" role="img" aria-labelledby="title">
  <title id="title">{title}</title>
  {content}
</svg>
'''
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(svg, encoding="utf-8")
    return output_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Export a Sketch shape group containing a layer UUID as SVG.")
    parser.add_argument("sketch_dir", type=Path, help="Extracted Sketch directory containing pages/")
    parser.add_argument("page_id", help="Sketch page UUID")
    parser.add_argument("layer_id", help="Target layer UUID")
    parser.add_argument("output_path", type=Path, help="Output SVG path")
    args = parser.parse_args()
    output_path = export_svg(args.sketch_dir, args.page_id, args.layer_id, args.output_path)
    print(f"SVG exported to: {output_path}")


if __name__ == "__main__":
    main()
