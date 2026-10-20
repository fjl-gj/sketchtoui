from __future__ import annotations

import json
from collections import Counter
from functools import lru_cache
from pathlib import Path
from typing import Any


DEFAULT_INPUT_PATH = Path("fixtures/sketch/test_001/test/注册页.related.json")
DEFAULT_OUTPUT_PATH = Path("fixtures/sketch/test_001/test/注册页.parsed.json")

LAYER_TYPES = {
    "group": "group",
    "text": "text",
    "rectangle": "rectangle",
    "oval": "oval",
    "shapeGroup": "shape_group",
    "shapePath": "shape_path",
    "bitmap": "image",
    "symbolInstance": "symbol_instance",
    "symbolMaster": "symbol_master",
    "artboard": "artboard",
}


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as source_file:
        return json.load(source_file)


def color_to_json(color: dict[str, Any] | None) -> dict[str, Any] | None:
    if not color:
        return None

    red = color.get("red")
    green = color.get("green")
    blue = color.get("blue")
    alpha = color.get("alpha", 1)
    result: dict[str, Any] = {
        "red": red,
        "green": green,
        "blue": blue,
        "alpha": alpha,
    }
    if all(isinstance(value, (int, float)) for value in (red, green, blue, alpha)):
        channels = [round(max(0, min(1, value)) * 255) for value in (red, green, blue)]
        alpha_channel = round(max(0, min(1, alpha)) * 255)
        result["hex"] = f"#{channels[0]:02X}{channels[1]:02X}{channels[2]:02X}"
        result["rgba"] = f"rgba({channels[0]}, {channels[1]}, {channels[2]}, {alpha:.3f})"
        result["hex8"] = f"#{channels[0]:02X}{channels[1]:02X}{channels[2]:02X}{alpha_channel:02X}"
    if color.get("swatchID"):
        result["swatchID"] = color["swatchID"]
    return result


def parse_gradient(gradient: dict[str, Any] | None) -> dict[str, Any] | None:
    if not gradient:
        return None
    return {
        "type": gradient.get("gradientType"),
        "from": gradient.get("from"),
        "to": gradient.get("to"),
        "ellipseLength": gradient.get("elipseLength"),
        "stops": [
            {
                "position": stop.get("position"),
                "color": color_to_json(stop.get("color")),
            }
            for stop in gradient.get("stops", [])
        ],
    }


def parse_fill(fill: dict[str, Any]) -> dict[str, Any]:
    image_reference = fill.get("image", {}).get("_ref")
    return {
        "enabled": fill.get("isEnabled", False),
        "type": fill.get("fillType"),
        "color": color_to_json(fill.get("color")),
        "gradient": parse_gradient(fill.get("gradient")),
        "opacity": fill.get("contextSettings", {}).get("opacity", 1),
        "image": {"reference": image_reference} if isinstance(image_reference, str) else None,
        "patternFillType": fill.get("patternFillType"),
        "patternTileScale": fill.get("patternTileScale"),
    }


def parse_style(layer: dict[str, Any]) -> dict[str, Any]:
    style = layer.get("style", {})
    context = style.get("contextSettings", {})
    fills = [parse_fill(fill) for fill in style.get("fills", [])]
    borders = [
        {
            "enabled": border.get("isEnabled", False),
            "type": border.get("fillType"),
            "color": color_to_json(border.get("color")),
            "gradient": parse_gradient(border.get("gradient")),
            "position": border.get("position"),
            "thickness": border.get("thickness"),
            "opacity": border.get("contextSettings", {}).get("opacity", 1),
        }
        for border in style.get("borders", [])
    ]
    shadows = [
        {
            "enabled": shadow.get("isEnabled", False),
            "color": color_to_json(shadow.get("color")),
            "offsetX": shadow.get("offsetX"),
            "offsetY": shadow.get("offsetY"),
            "blurRadius": shadow.get("blurRadius"),
            "spread": shadow.get("spread"),
        }
        for shadow in style.get("shadows", [])
    ]
    corners = style.get("corners", {})
    blur = next((item for item in style.get("blurs", []) if item.get("isEnabled", False)), None)
    return {
        "opacity": context.get("opacity", 1),
        "blendMode": context.get("blendMode", 0),
        "windingRule": style.get("windingRule"),
        "fills": fills,
        "borders": borders,
        "shadows": shadows,
        "blur": {
            "type": blur.get("type"),
            "radius": blur.get("radius"),
            "saturation": blur.get("saturation"),
            "center": blur.get("center"),
        } if blur else None,
        "cornerRadii": corners.get("radii", []),
    }


def font_css_family(font_name: str | None) -> str | None:
    if not font_name:
        return None
    if font_name.startswith("PingFangSC-"):
        return "PingFang SC"
    return font_name


def font_weight(font_name: str | None) -> int | None:
    if not font_name:
        return None
    normalized = font_name.lower()
    if "thin" in normalized or "ultralight" in normalized:
        return 100
    if "extralight" in normalized:
        return 200
    if "light" in normalized:
        return 300
    if "medium" in normalized:
        return 500
    if "semibold" in normalized or "demibold" in normalized:
        return 600
    if "bold" in normalized:
        return 700
    if "black" in normalized or "heavy" in normalized:
        return 900
    if "regular" in normalized or "normal" in normalized:
        return 400
    return None


def parse_text(layer: dict[str, Any]) -> dict[str, Any]:
    attributed_string = layer.get("attributedString", {})
    content = attributed_string.get("string", "")
    line_count = max(1, content.count("\n") + 1)
    fallback_line_height = (layer.get("frame", {}).get("height") or 0) / line_count
    runs = []
    for item in attributed_string.get("attributes", []):
        attributes = item.get("attributes", {})
        font = attributes.get("MSAttributedStringFontAttribute", {}).get("attributes", {})
        font_name = font.get("name")
        paragraph = attributes.get("paragraphStyle", {})
        maximum_line_height = paragraph.get("maximumLineHeight")
        minimum_line_height = paragraph.get("minimumLineHeight")
        runs.append(
            {
                "location": item.get("location"),
                "length": item.get("length"),
                "font": {
                    "name": font_name,
                    "cssFamily": font_css_family(font_name),
                    "size": font.get("size"),
                    "weight": font_weight(font_name),
                },
                "color": color_to_json(attributes.get("MSAttributedStringColorAttribute")),
                "alignment": paragraph.get("alignment"),
                "lineHeight": maximum_line_height or minimum_line_height or fallback_line_height,
                "minimumLineHeight": minimum_line_height,
                "maximumLineHeight": maximum_line_height,
                "kerning": attributes.get("kerning", attributes.get("NSKern")),
                "underlineStyle": attributes.get("underlineStyle"),
                "strikethroughStyle": attributes.get("strikethroughStyle"),
                "textTransform": attributes.get("MSAttributedStringTextTransformAttribute"),
                "verticalAlignment": attributes.get("textStyleVerticalAlignmentKey"),
                "paragraph": {
                    "headIndent": paragraph.get("headIndent"),
                    "tabStops": paragraph.get("tabStops"),
                    "textLists": paragraph.get("textLists"),
                },
            }
        )
    return {"content": content, "runs": runs}


def has_visible_paint(node: dict[str, Any]) -> bool:
    if node.get("type") in {"text", "image", "rectangle", "shape_path", "unknown", "symbol_instance"}:
        return True
    style = node.get("style", {})
    return any(fill.get("enabled") for fill in style.get("fills", [])) or any(
        border.get("enabled") for border in style.get("borders", [])
    )


def apply_visual_frame(node: dict[str, Any]) -> None:
    visual_frames = []
    if node.get("visible", True) and has_visible_paint(node):
        visual_frames.append(node["frame"])
    for child in node.get("children", []):
        visual_frame = child.get("visualFrame")
        if child.get("visible", True) and visual_frame:
            visual_frames.append(visual_frame)
    if not visual_frames:
        return
    left = min(frame["absoluteX"] for frame in visual_frames)
    top = min(frame["absoluteY"] for frame in visual_frames)
    right = max(frame["absoluteX"] + frame["width"] for frame in visual_frames)
    bottom = max(frame["absoluteY"] + frame["height"] for frame in visual_frames)
    node["visualFrame"] = {
        "x": left - node["frame"]["absoluteX"],
        "y": top - node["frame"]["absoluteY"],
        "width": right - left,
        "height": bottom - top,
        "absoluteX": left,
        "absoluteY": top,
    }


def parse_image(layer: dict[str, Any], sketch_dir: Path) -> dict[str, Any] | None:
    reference = layer.get("image", {}).get("_ref")
    if not isinstance(reference, str):
        return None
    image_path = sketch_dir / reference
    return {
        "reference": reference,
        "path": str(image_path),
        "exists": image_path.is_file(),
    }


def parse_shape_points(layer: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "point": point.get("point"),
            "curveFrom": point.get("curveFrom"),
            "curveTo": point.get("curveTo"),
            "hasCurveFrom": point.get("hasCurveFrom", False),
            "hasCurveTo": point.get("hasCurveTo", False),
            "curveMode": point.get("curveMode"),
            "cornerRadius": point.get("cornerRadius"),
        }
        for point in layer.get("points", [])
    ]


@lru_cache(maxsize=8)
def symbol_masters_for(sketch_dir: Path) -> dict[str, dict[str, Any]]:
    masters: dict[str, dict[str, Any]] = {}

    def visit(layer: dict[str, Any]) -> None:
        if layer.get("_class") == "symbolMaster" and isinstance(layer.get("symbolID"), str):
            masters[layer["symbolID"]] = layer
        for child in layer.get("layers", []):
            visit(child)

    for page_path in (sketch_dir / "pages").glob("*.json"):
        try:
            page = load_json(page_path)
        except (OSError, json.JSONDecodeError):
            continue
        for root_layer in page.get("layers", []):
            visit(root_layer)
    return masters


def symbol_overrides(layer: dict[str, Any]) -> dict[str, dict[str, Any]]:
    values: dict[str, dict[str, Any]] = {}
    for override in layer.get("overrideValues", []):
        name = override.get("overrideName")
        value = override.get("value")
        if not isinstance(name, str) or "_" not in name:
            continue
        layer_id, key = name.split("_", 1)
        if not layer_id:
            continue
        target = values.setdefault(layer_id, {})
        if key == "stringValue" and isinstance(value, str):
            target["stringValue"] = value
        elif key == "textColor" and isinstance(value, dict):
            target["textColor"] = color_to_json(value)
        elif key.startswith("color:") and isinstance(value, dict):
            target[key] = color_to_json(value)
    return values


def apply_style_overrides(style: dict[str, Any], overrides: dict[str, Any] | None) -> dict[str, Any]:
    if not overrides:
        return style
    for key, color in overrides.items():
        if not key.startswith("color:") or not isinstance(color, dict):
            continue
        target, _, index = key.removeprefix("color:").partition("-")
        if not index.isdigit():
            continue
        collection = style.get(f"{target}s")
        if isinstance(collection, list) and int(index) < len(collection):
            collection[int(index)]["color"] = color
    return style


def parse_layer(
    layer: dict[str, Any],
    sketch_dir: Path,
    parent_x: float = 0,
    parent_y: float = 0,
    is_design_page: bool = False,
    parent_id: str | None = None,
    scale_x: float = 1,
    scale_y: float = 1,
    symbol_depth: int = 0,
    overrides: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    source_frame = layer.get("frame", {})
    local_x = source_frame.get("x", 0) * scale_x
    local_y = source_frame.get("y", 0) * scale_y
    absolute_x = 0 if is_design_page else parent_x + local_x
    absolute_y = 0 if is_design_page else parent_y + local_y

    layer_override = (overrides or {}).get(str(layer.get("do_objectID") or ""), {})
    result: dict[str, Any] = {
        "id": layer.get("do_objectID"),
        "name": layer.get("name"),
        "type": "design_page" if is_design_page else LAYER_TYPES.get(layer.get("_class"), "unknown"),
        "sketchClass": layer.get("_class"),
        "visible": layer.get("isVisible", True),
        "locked": layer.get("isLocked", False),
        "parentId": parent_id,
        "childCount": len(layer.get("layers", [])),
        "isMask": layer.get("hasClippingMask", False),
        "clippingMaskMode": layer.get("clippingMaskMode", 0),
        "breaksMaskChain": layer.get("shouldBreakMaskChain", False),
        "hasClickThrough": layer.get("hasClickThrough", False),
        "resizingConstraint": layer.get("resizingConstraint", 0),
        "rotation": layer.get("rotation", 0),
        "booleanOperation": layer.get("booleanOperation", -1),
        "flippedHorizontal": layer.get("isFlippedHorizontal", False),
        "flippedVertical": layer.get("isFlippedVertical", False),
        "frame": {
            "x": 0 if is_design_page else local_x,
            "y": 0 if is_design_page else local_y,
            "width": source_frame.get("width", 0) * scale_x,
            "height": source_frame.get("height", 0) * scale_y,
            "absoluteX": absolute_x,
            "absoluteY": absolute_y,
        },
        "sourceFrame": source_frame,
        "style": apply_style_overrides(parse_style(layer), layer_override),
    }

    if is_design_page:
        result["backgroundColor"] = color_to_json(layer.get("backgroundColor"))
        result["exportFormats"] = layer.get("exportOptions", {}).get("exportFormats", [])
    if layer.get("_class") == "text":
        result["text"] = parse_text(layer)
        override_value = layer_override.get("stringValue")
        if isinstance(override_value, str):
            result["text"]["content"] = override_value
            if result["text"].get("runs"):
                result["text"]["runs"][0]["length"] = len(override_value)
        if isinstance(layer_override.get("textColor"), dict):
            for run in result["text"].get("runs", []):
                run["color"] = layer_override["textColor"]
    if layer.get("_class") == "bitmap":
        result["image"] = parse_image(layer, sketch_dir)
    if layer.get("_class") == "shapePath":
        result["points"] = parse_shape_points(layer)
    if layer.get("symbolID"):
        result["symbolID"] = layer["symbolID"]

    children = layer.get("layers", [])
    child_scale_x = scale_x
    child_scale_y = scale_y
    child_overrides = overrides
    if layer.get("_class") == "symbolInstance" and not children and symbol_depth < 4:
        master = symbol_masters_for(sketch_dir).get(layer.get("symbolID"))
        master_frame = master.get("frame", {}) if master else {}
        master_width = float(master_frame.get("width") or 0)
        master_height = float(master_frame.get("height") or 0)
        if master and master_width > 0 and master_height > 0:
            children = master.get("layers", [])
            child_scale_x = result["frame"]["width"] / master_width
            child_scale_y = result["frame"]["height"] / master_height
            child_overrides = {**(overrides or {}), **symbol_overrides(layer)}
            result["symbolMasterId"] = master.get("do_objectID")
            result["symbolMasterName"] = master.get("name")
            result["childCount"] = len(children)
    if children:
        result["children"] = [
            parse_layer(
                child,
                sketch_dir,
                absolute_x,
                absolute_y,
                parent_id=result["id"],
                scale_x=child_scale_x,
                scale_y=child_scale_y,
                symbol_depth=symbol_depth + (1 if layer.get("_class") == "symbolInstance" else 0),
                overrides=child_overrides,
            )
            for child in children
        ]

    apply_visual_frame(result)
    return result


def collect_statistics(layer: dict[str, Any]) -> dict[str, Any]:
    counts: Counter[str] = Counter()
    visible_count = 0

    def visit(node: dict[str, Any]) -> None:
        nonlocal visible_count
        counts[node["type"]] += 1
        if node["visible"]:
            visible_count += 1
        for child in node.get("children", []):
            visit(child)

    visit(layer)
    return {
        "totalLayers": sum(counts.values()),
        "visibleLayers": visible_count,
        "byType": dict(sorted(counts.items())),
    }


def parse_design_page(input_path: Path, output_path: Path) -> dict[str, Any]:
    source = load_json(Path(input_path))
    sketch_dir = Path(source["source"]["sketchDirectory"])
    artboard = source["artboard"]
    parsed_page = parse_layer(artboard, sketch_dir, is_design_page=True)

    result = {
        "source": {
            "linkedJson": str(input_path),
            "pageFile": source["source"]["pageFile"],
            "pageID": source["ids"]["pageID"],
            "artboardID": source["ids"]["artboardID"],
        },
        "designPage": parsed_page,
        "statistics": collect_statistics(parsed_page),
    }

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as output_file:
        json.dump(result, output_file, ensure_ascii=False, indent=2)
        output_file.write("\n")
    return result


def main() -> None:
    result = parse_design_page(DEFAULT_INPUT_PATH, DEFAULT_OUTPUT_PATH)
    print(f"Parsed: {result['designPage']['name']}")
    print(f"Output: {DEFAULT_OUTPUT_PATH}")


if __name__ == "__main__":
    main()
