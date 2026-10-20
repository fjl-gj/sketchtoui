from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any


DEFAULT_SKETCH_DIR = Path("fixtures/sketch/test_001/test")
DEFAULT_PAGE_ID = "748D2293-E71E-4046-BCB8-DAFFC5467DAC"
DEFAULT_ARTBOARD_ID = "15CA73EA-60A5-4655-B3CE-03BA2A15C757"
DEFAULT_OUTPUT_PATH = DEFAULT_SKETCH_DIR / "注册页.related.json"


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as source_file:
        return json.load(source_file)


def find_object_by_id(value: Any, object_id: str) -> dict[str, Any] | None:
    if isinstance(value, dict):
        if value.get("do_objectID") == object_id:
            return value
        for child in value.values():
            found = find_object_by_id(child, object_id)
            if found is not None:
                return found
    elif isinstance(value, list):
        for child in value:
            found = find_object_by_id(child, object_id)
            if found is not None:
                return found
    return None


def extract_uuid_chain(
    sketch_dir: Path,
    page_id: str,
    artboard_id: str,
    output_path: Path,
) -> dict[str, Any]:
    """Extract only the JSON fragments connected by a page and artboard UUID."""
    sketch_dir = Path(sketch_dir)
    document = load_json(sketch_dir / "document.json")
    meta = load_json(sketch_dir / "meta.json")
    user = load_json(sketch_dir / "user.json")

    page_meta = meta.get("pagesAndArtboards", {}).get(page_id)
    if page_meta is None:
        raise ValueError(f"Page {page_id} was not found in meta.json.")

    artboard_meta = page_meta.get("artboards", {}).get(artboard_id)
    if artboard_meta is None:
        raise ValueError(f"Artboard {artboard_id} was not found under page {page_id} in meta.json.")

    page_reference = next(
        (
            item
            for item in document.get("pages", [])
            if item.get("_ref") == f"pages/{page_id}"
        ),
        None,
    )
    if page_reference is None:
        raise ValueError(f"Page {page_id} was not referenced by document.json.")

    page_path = sketch_dir / f"{page_reference['_ref']}.json"
    page = load_json(page_path)
    artboard_data = find_object_by_id(page.get("layers", []), artboard_id)
    if artboard_data is None:
        raise ValueError(f"Artboard {artboard_id} was not found in {page_path}.")

    page_context = {key: deepcopy(value) for key, value in page.items() if key != "layers"}
    result = {
        "source": {
            "sketchDirectory": str(sketch_dir),
            "documentFile": str(sketch_dir / "document.json"),
            "metaFile": str(sketch_dir / "meta.json"),
            "userFile": str(sketch_dir / "user.json"),
            "pageFile": str(page_path),
        },
        "ids": {
            "pageID": page_id,
            "artboardID": artboard_id,
        },
        "meta": {
            "page": {
                "name": page_meta.get("name"),
                "artboards": {artboard_id: deepcopy(artboard_meta)},
            }
        },
        "document": {
            "pageReference": deepcopy(page_reference),
        },
        "user": {
            "page": deepcopy(user.get(page_id)),
            "artboard": deepcopy(user.get(artboard_id)),
        },
        "page": page_context,
        "artboard": deepcopy(artboard_data),
    }

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as output_file:
        json.dump(result, output_file, ensure_ascii=False, indent=2)
        output_file.write("\n")

    return result


def main() -> None:
    result = extract_uuid_chain(
        sketch_dir=DEFAULT_SKETCH_DIR,
        page_id=DEFAULT_PAGE_ID,
        artboard_id=DEFAULT_ARTBOARD_ID,
        output_path=DEFAULT_OUTPUT_PATH,
    )
    print(f"Extracted: {result['meta']['page']['artboards'][DEFAULT_ARTBOARD_ID]['name']}")
    print(f"Output: {DEFAULT_OUTPUT_PATH}")


if __name__ == "__main__":
    main()
