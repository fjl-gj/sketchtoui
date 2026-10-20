from __future__ import annotations

import argparse
import shutil
import zipfile
from pathlib import Path
from typing import Any, Dict


ROOT_PATH = Path("fixtures/sketch")


def sketch_to_json(sketch_path: Path, output_path: Path) -> Dict[str, Any]:
    """Copy a Sketch archive as a ZIP file and extract it into ``output_path``.

    The source ``.sketch`` file is never moved or modified.
    """
    sketch_path = Path(sketch_path)
    output_path = Path(output_path)

    if not sketch_path.is_file():
        raise FileNotFoundError(f"Sketch file not found: {sketch_path}")

    output_path.mkdir(parents=True, exist_ok=True)
    zip_path = sketch_path.parent / f"{sketch_path.stem}.zip"
    shutil.copy2(sketch_path, zip_path)

    with zipfile.ZipFile(zip_path) as archive:
        archive.extractall(output_path)

    return {
        "sketch_path": str(sketch_path),
        "zip_path": str(zip_path),
        "output_path": str(output_path),
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Copy a .sketch file as a ZIP archive and extract it."
    )
    parser.add_argument("sketch_path", type=Path, help="Source .sketch file")
    parser.add_argument("output_path", type=Path, help="Directory for the ZIP and extracted files")
    args = parser.parse_args()

    result = sketch_to_json(args.sketch_path, args.output_path)
    print(f"ZIP copied to: {result['zip_path']}")
    print(f"Extracted to: {result['output_path']}")


if __name__ == "__main__":
    sketch_path = Path("fixtures/sketch/test_001/GoGoTrack260629.sketch")
    output_path = Path("fixtures/sketch/test_001/test")

    result = sketch_to_json(sketch_path, output_path)
    print(f"ZIP copied to: {result['zip_path']}")
    # main()
