from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any, Iterator


DEFAULT_SKETCH_DIR = Path("fixtures/sketch/test_001/test")
DEFAULT_LAYER_NAME = "注册页"
DEFAULT_OUTPUT_PATH = DEFAULT_SKETCH_DIR / "注册页.related.json"

REFERENCE_KEYS = {
    "swatchID",
    "sharedStyleID",
    "symbolID",
    "textStyleID",
    "layerStyleID",
}


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as source_file:
        return json.load(source_file)


def find_layer_by_id(value: Any, object_id: str) -> dict[str, Any] | None:
    if isinstance(value, dict):
        if value.get("do_objectID") == object_id:
            return value
        for child in value.values():
            layer = find_layer_by_id(child, object_id)
            if layer is not None:
                return layer
    elif isinstance(value, list):
        for child in value:
            layer = find_layer_by_id(child, object_id)
            if layer is not None:
                return layer
    return None


def iter_objects(value: Any) -> Iterator[dict[str, Any]]:
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from iter_objects(child)
    elif isinstance(value, list):
        for child in value:
            yield from iter_objects(child)


def collect_references(layer: dict[str, Any]) -> dict[str, list[str]]:
    references: dict[str, set[str]] = {}

    for item in iter_objects(layer):
        for key, value in item.items():
            if key in REFERENCE_KEYS and isinstance(value, str) and value:
                references.setdefault(key, set()).add(value)
        if item.get("_class") == "MSJSONFileReference":
            reference = item.get("_ref")
            if isinstance(reference, str) and reference:
                references.setdefault("fileReferences", set()).add(reference)

    return {key: sorted(values) for key, values in sorted(references.items())}


def find_target(meta: dict[str, Any], layer_name: str) -> tuple[str, str, dict[str, Any]]:
    matches: list[tuple[str, str, dict[str, Any]]] = []

    for page_id, page_meta in meta.get("pagesAndArtboards", {}).items():
        for layer_id, layer_meta in page_meta.get("artboards", {}).items():
            if layer_meta.get("name") == layer_name:
                matches.append((page_id, layer_id, page_meta))

    if not matches:
        raise ValueError(f"No artboard or group named {layer_name!r} exists in meta.json.")
    if len(matches) > 1:
        locations = ", ".join(f"{page_id}/{layer_id}" for page_id, layer_id, _ in matches)
        raise ValueError(f"The name {layer_name!r} is ambiguous: {locations}")

    return matches[0]


def matching_objects(objects: list[dict[str, Any]], object_ids: set[str]) -> list[dict[str, Any]]:
    return [deepcopy(item) for item in objects if item.get("do_objectID") in object_ids]


def matching_foreign_swatches(
    foreign_swatches: list[dict[str, Any]], swatch_ids: set[str]
) -> list[dict[str, Any]]:
    matches = []
    for swatch in foreign_swatches:
        local_swatch = swatch.get("localSwatch", {})
        if (
            local_swatch.get("do_objectID") in swatch_ids
            or swatch.get("remoteSwatchID") in swatch_ids
        ):
            matches.append(deepcopy(swatch))
    return matches


def find_symbol_masters(sketch_dir: Path, symbol_ids: set[str]) -> list[dict[str, Any]]:
    if not symbol_ids:
        return []

    matches = []
    for page_path in (sketch_dir / "pages").glob("*.json"):
        page = load_json(page_path)
        for item in iter_objects(page):
            if item.get("_class") == "symbolMaster" and item.get("symbolID") in symbol_ids:
                matches.append(deepcopy(item))
    return matches


def matching_foreign_symbols(
    foreign_symbols: list[dict[str, Any]], symbol_ids: set[str]
) -> list[dict[str, Any]]:
    matches = []
    for symbol in foreign_symbols:
        masters = (symbol.get("symbolMaster", {}), symbol.get("originalMaster", {}))
        if any(master.get("symbolID") in symbol_ids for master in masters):
            matches.append(deepcopy(symbol))
    return matches


def extract_layer_structure(
    sketch_dir: Path,
    layer_name: str,
    output_path: Path,
) -> dict[str, Any]:
    sketch_dir = Path(sketch_dir)
    document = load_json(sketch_dir / "document.json")
    meta = load_json(sketch_dir / "meta.json")

    page_id, layer_id, page_meta = find_target(meta, layer_name)
    page_path = sketch_dir / "pages" / f"{page_id}.json"
    page = load_json(page_path)
    layer = find_layer_by_id(page, layer_id)
    if layer is None:
        raise ValueError(f"Layer {layer_id} is indexed in meta.json but absent from {page_path}.")

    references = collect_references(layer)
    swatch_ids = set(references.get("swatchID", []))
    layer_style_ids = set(references.get("sharedStyleID", [])) | set(
        references.get("layerStyleID", [])
    )
    text_style_ids = set(references.get("textStyleID", []))
    symbol_ids = set(references.get("symbolID", []))
    image_references = references.get("fileReferences", [])

    page_context = {key: deepcopy(value) for key, value in page.items() if key != "layers"}
    document_context = {
        key: deepcopy(document[key])
        for key in ("_class", "do_objectID", "colorSpace", "currentPageIndex")
        if key in document
    }
    document_context["assets"] = deepcopy(document.get("assets", {}))

    result = {
        "source": {
            "sketchDirectory": str(sketch_dir),
            "pageFile": str(page_path),
            "documentFile": str(sketch_dir / "document.json"),
            "metaFile": str(sketch_dir / "meta.json"),
        },
        "target": {
            "pageID": page_id,
            "pageName": page_meta.get("name"),
            "layerID": layer_id,
            "layerName": layer.get("name"),
            "layerClass": layer.get("_class"),
        },
        "pageContext": page_context,
        "meta": {
            "pageAndArtboards": deepcopy(page_meta),
            "format": {
                key: deepcopy(meta[key])
                for key in ("app", "appVersion", "build", "version", "compatibilityVersion")
                if key in meta
            },
        },
        "documentContext": document_context,
        "layer": deepcopy(layer),
        "references": references,
        "dependencies": {
            "imageFiles": [
                {
                    "reference": reference,
                    "path": str(sketch_dir / reference),
                    "exists": (sketch_dir / reference).is_file(),
                }
                for reference in image_references
            ],
            "sharedSwatches": matching_objects(
                document.get("sharedSwatches", {}).get("objects", []), swatch_ids
            ),
            "foreignSwatches": matching_foreign_swatches(
                document.get("foreignSwatches", []), swatch_ids
            ),
            "sharedLayerStyles": matching_objects(
                document.get("layerStyles", {}).get("objects", []), layer_style_ids
            ),
            "sharedTextStyles": matching_objects(
                document.get("layerTextStyles", {}).get("objects", []), text_style_ids
            ),
            "localSymbolMasters": find_symbol_masters(sketch_dir, symbol_ids),
            "foreignSymbols": matching_foreign_symbols(
                document.get("foreignSymbols", []), symbol_ids
            ),
        },
    }

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as output_file:
        json.dump(result, output_file, ensure_ascii=False, indent=2)
        output_file.write("\n")

    return result


def main() -> None:
    result = extract_layer_structure(
        sketch_dir=DEFAULT_SKETCH_DIR,
        layer_name=DEFAULT_LAYER_NAME,
        output_path=DEFAULT_OUTPUT_PATH,
    )
    print(f"Extracted: {result['target']['layerName']}")
    print(f"Output: {DEFAULT_OUTPUT_PATH}")


if __name__ == "__main__":
    main()
