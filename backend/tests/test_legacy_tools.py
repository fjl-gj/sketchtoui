from __future__ import annotations

import io
import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import sketch_extract_artboard
import sketch_layer_to_svg
import sketch_page_to_canvas
import sketch_to_canvas
import sketch_to_canvas_site
import sketch_to_json
import sketch_to_struct


PAGE_ID = "PAGE"
ARTBOARD_ID = "ARTBOARD"
PLUGIN_PAGE_ID = "PLUGIN"


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


def shape_group(layer_id: str = "ICON") -> dict:
    return {
        "_class": "shapeGroup",
        "do_objectID": layer_id,
        "name": "<Icon>",
        "isVisible": True,
        "frame": {"x": 5, "y": 8, "width": 20, "height": 20},
        "style": {"fills": [{"isEnabled": True, "fillType": 0, "color": {"red": 1, "green": 0, "blue": 0, "alpha": 1}}]},
        "layers": [
            {
                "_class": "shapePath",
                "do_objectID": "PATH",
                "isVisible": True,
                "frame": {"x": 0, "y": 0, "width": 20, "height": 20},
                "points": [
                    {"point": "{0, 0}"},
                    {"point": "{1, 0}"},
                    {"point": "{1, 1}"},
                    {"point": "{0, 1}"},
                ],
            }
        ],
    }


def artboard(artboard_id: str, name: str, x: int, children: list[dict] | None = None) -> dict:
    return {
        "_class": "artboard",
        "do_objectID": artboard_id,
        "name": name,
        "isVisible": True,
        "frame": {"x": x, "y": 20, "width": 200, "height": 120},
        "layers": children if children is not None else [shape_group()],
    }


def make_sketch(root: Path) -> None:
    page_layers = [
        artboard(ARTBOARD_ID, "Desktop login", 10),
        artboard("MOBILE", "H5 login", 260),
    ]
    plugin_layers = [artboard("PLUGIN_ART", "Plugin dialog", 0)]
    write_json(root / "document.json", {"_class": "document", "do_objectID": "DOC", "pages": [{"_ref": f"pages/{PAGE_ID}"}, {"_ref": f"pages/{PLUGIN_PAGE_ID}"}], "assets": {}})
    write_json(root / "user.json", {"name": "tester"})
    write_json(
        root / "meta.json",
        {
            "app": "Sketch",
            "pagesAndArtboards": {
                PAGE_ID: {"name": "登录", "artboards": {ARTBOARD_ID: {"name": "Desktop login"}, "MOBILE": {"name": "H5 login"}}},
                PLUGIN_PAGE_ID: {"name": "插件", "artboards": {"PLUGIN_ART": {"name": "Plugin dialog"}}},
            },
        },
    )
    write_json(root / "pages" / f"{PAGE_ID}.json", {"_class": "page", "do_objectID": PAGE_ID, "layers": page_layers})
    write_json(root / "pages" / f"{PLUGIN_PAGE_ID}.json", {"_class": "page", "do_objectID": PLUGIN_PAGE_ID, "layers": plugin_layers})
    (root / "images").mkdir(parents=True, exist_ok=True)
    (root / "images" / "icon.png").write_bytes(b"image")
    (root / "previews").mkdir(parents=True, exist_ok=True)
    (root / "previews" / "preview.png").write_bytes(b"preview")


class LegacyToolTests(unittest.TestCase):
    def test_archive_extractor_and_canvas_preview(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.sketch"
            with zipfile.ZipFile(source, "w") as archive:
                archive.writestr("document.json", "{}")
            result = sketch_to_json.sketch_to_json(source, root / "extracted")
            self.assertTrue(Path(result["zip_path"]).is_file())
            self.assertTrue((root / "extracted" / "document.json").is_file())
            with self.assertRaises(FileNotFoundError):
                sketch_to_json.sketch_to_json(root / "missing.sketch", root / "out")

            page_json = root / "page.json"
            page_json.write_text('{"name": "</script>"}', encoding="utf-8")
            output = sketch_to_canvas.generate_canvas_preview(page_json, root / "preview" / "index.html")
            self.assertIn("<\\/script>", output.read_text(encoding="utf-8"))

    def test_artboard_structure_svg_and_canvas_generators(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "sketch"
            make_sketch(root)
            related = sketch_extract_artboard.extract_uuid_chain(root, PAGE_ID, ARTBOARD_ID, root / "related.json")
            self.assertEqual(related["artboard"]["do_objectID"], ARTBOARD_ID)
            self.assertEqual(related["meta"]["page"]["name"], "登录")
            with self.assertRaises(ValueError):
                sketch_extract_artboard.extract_uuid_chain(root, "missing", ARTBOARD_ID, root / "missing.json")

            structured = sketch_to_struct.extract_layer_structure(root, "Desktop login", root / "structure.json")
            self.assertEqual(structured["target"]["layerID"], ARTBOARD_ID)
            self.assertTrue((root / "structure.json").is_file())
            with self.assertRaises(ValueError):
                sketch_to_struct.find_target({"pagesAndArtboards": {}}, "missing")
            with self.assertRaises(ValueError):
                sketch_to_struct.find_target({"pagesAndArtboards": {"A": {"artboards": {"1": {"name": "same"}}}, "B": {"artboards": {"2": {"name": "same"}}}}}, "same")

            svg_path = sketch_layer_to_svg.export_svg(root, PAGE_ID, "PATH", root / "icon.svg")
            svg = svg_path.read_text(encoding="utf-8")
            self.assertIn("fill=\"#FF0000\"", svg)
            self.assertIn("&lt;Icon&gt;", svg)
            self.assertEqual(sketch_layer_to_svg.parse_point("{1.5, 2}"), (1.5, 2.0))
            self.assertEqual(sketch_layer_to_svg.color_value(None), None)
            self.assertEqual(sketch_layer_to_svg.render_layer({"_class": "shapePath", "isVisible": False}), "")

            canvas = sketch_page_to_canvas.build_page_canvas(root, PAGE_ID)
            self.assertEqual(len(canvas["designPages"]), 2)
            self.assertEqual(canvas["bounds"]["minX"], 10)
            sketch_page_to_canvas.write_json(root / "canvas.json", canvas)
            sketch_page_to_canvas.write_preview(root / "canvas.html", canvas)
            self.assertTrue((root / "canvas.html").is_file())

    def test_canvas_site_groups_platforms_and_helpers(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "sketch"
            output = Path(directory) / "canvas"
            make_sketch(root)
            progress: list[tuple[int, int, str]] = []
            groups = sketch_to_canvas_site.generate_canvas_site(root, output, lambda *args: progress.append(args))
            self.assertEqual({group["platform"] for group in groups}, {"desktop", "mobile", "plugin"})
            self.assertEqual(len(progress), 3)
            manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(len(manifest["previews"]), 1)
            self.assertTrue((output / "_shared" / "renderer.js").is_file())
            self.assertTrue(all((output / item["directory"] / "canvas.json").is_file() for item in groups))
            existing: set[str] = set()
            self.assertEqual(sketch_to_canvas_site.safe_directory_name("a/b", existing), "a_b")
            self.assertEqual(sketch_to_canvas_site.safe_directory_name("A_B", existing), "A_B-2")
            self.assertEqual(sketch_to_canvas_site.group_platform("插件版", "H5 ignored"), "plugin")
            self.assertEqual(sketch_to_canvas_site.group_platform("登录", " H5 注册"), "mobile")


if __name__ == "__main__":
    unittest.main()
