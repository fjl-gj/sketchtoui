from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from sketch_to_page_json import (
    apply_visual_frame,
    color_to_json,
    collect_statistics,
    font_css_family,
    font_weight,
    parse_design_page,
    parse_layer,
    parse_style,
    parse_text,
    symbol_masters_for,
    symbol_overrides,
)


class SketchPageJsonTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.sketch_dir = Path(self.temporary_directory.name)

    def tearDown(self) -> None:
        symbol_masters_for.cache_clear()
        self.temporary_directory.cleanup()

    def test_symbol_overrides_replace_text_and_style_colors(self) -> None:
        overrides = symbol_overrides(
            {
                "overrideValues": [
                    {"overrideName": "TEXT_stringValue", "value": "Overridden"},
                    {"overrideName": "TEXT_textColor", "value": {"red": 1, "green": 0, "blue": 0, "alpha": 1}},
                    {"overrideName": "RECT_color:border-0", "value": {"red": 0, "green": 1, "blue": 0, "alpha": 1}},
                ]
            }
        )
        text = parse_layer(
            {
                "_class": "text",
                "do_objectID": "TEXT",
                "frame": {"x": 0, "y": 0, "width": 100, "height": 20},
                "attributedString": {
                    "string": "Original",
                    "attributes": [
                        {
                            "location": 0,
                            "length": 8,
                            "attributes": {
                                "MSAttributedStringFontAttribute": {"attributes": {"name": "PingFangSC-Regular", "size": 14}},
                                "MSAttributedStringColorAttribute": {"red": 0, "green": 0, "blue": 0, "alpha": 1},
                            },
                        }
                    ],
                },
            },
            self.sketch_dir,
            overrides=overrides,
        )
        rectangle = parse_layer(
            {
                "_class": "rectangle",
                "do_objectID": "RECT",
                "frame": {"x": 0, "y": 0, "width": 10, "height": 10},
                "style": {
                    "borders": [
                        {
                            "isEnabled": True,
                            "fillType": 0,
                            "color": {"red": 1, "green": 0, "blue": 0, "alpha": 1},
                            "thickness": 1,
                        }
                    ]
                },
            },
            self.sketch_dir,
            overrides=overrides,
        )

        self.assertEqual(text["text"]["content"], "Overridden")
        self.assertEqual(text["text"]["runs"][0]["color"]["hex"], "#FF0000")
        self.assertEqual(rectangle["style"]["borders"][0]["color"]["hex"], "#00FF00")

    def test_shape_path_preserves_curve_control_points(self) -> None:
        node = parse_layer(
            {
                "_class": "shapePath",
                "do_objectID": "PATH",
                "frame": {"x": 0, "y": 0, "width": 14, "height": 14},
                "points": [
                    {
                        "point": "{1, 0.5}",
                        "curveFrom": "{1, 0.776}",
                        "curveTo": "{1, 0.224}",
                        "curveMode": 2,
                    }
                ],
            },
            self.sketch_dir,
        )

        self.assertEqual(node["type"], "shape_path")
        self.assertEqual(node["points"][0]["curveMode"], 2)
        self.assertEqual(node["points"][0]["curveFrom"], "{1, 0.776}")

    def test_style_text_visual_frame_and_statistics_are_normalized(self) -> None:
        style = parse_style(
            {
                "style": {
                    "contextSettings": {"opacity": 0.6, "blendMode": 2},
                    "windingRule": 0,
                    "fills": [{"isEnabled": True, "fillType": 1, "color": {"red": 1, "green": 0, "blue": 0}, "gradient": {"gradientType": 0, "from": "{0, 0}", "to": "{1, 1}", "stops": [{"position": 0, "color": {"red": 0, "green": 0, "blue": 0}}]}}],
                    "borders": [{"isEnabled": True, "fillType": 0, "color": {"red": 0, "green": 1, "blue": 0}, "thickness": 2, "position": 1, "contextSettings": {"opacity": 0.5}}],
                    "shadows": [{"isEnabled": True, "color": {"red": 0, "green": 0, "blue": 0, "alpha": 0.2}, "offsetX": 1, "offsetY": 2, "blurRadius": 3, "spread": 4}],
                    "corners": {"radii": [4, 5]},
                    "blurs": [{"isEnabled": True, "type": 0, "radius": 8, "saturation": 1, "center": "{0.5, 0.5}"}],
                }
            }
        )
        text = parse_text(
            {
                "frame": {"height": 40},
                "attributedString": {
                    "string": "A\nB",
                    "attributes": [{"location": 0, "length": 3, "attributes": {"MSAttributedStringFontAttribute": {"attributes": {"name": "PingFangSC-Semibold", "size": 14}}, "MSAttributedStringColorAttribute": {"red": 0.2, "green": 0.4, "blue": 0.6, "alpha": 0.5}, "paragraphStyle": {"alignment": 1, "minimumLineHeight": 20}, "NSKern": 1.5, "underlineStyle": 1, "strikethroughStyle": 1, "MSAttributedStringTextTransformAttribute": "uppercase", "textStyleVerticalAlignmentKey": 1}}],
                },
            }
        )
        parent = {"type": "group", "visible": True, "frame": {"absoluteX": 10, "absoluteY": 10, "width": 1, "height": 1}, "style": {}, "children": [{"visible": True, "visualFrame": {"absoluteX": 5, "absoluteY": 6, "width": 20, "height": 30}}]}
        apply_visual_frame(parent)

        self.assertEqual(style["fills"][0]["gradient"]["stops"][0]["color"]["hex"], "#000000")
        self.assertEqual(style["borders"][0]["opacity"], 0.5)
        self.assertEqual(style["blur"]["radius"], 8)
        self.assertEqual(text["runs"][0]["font"]["cssFamily"], "PingFang SC")
        self.assertEqual(text["runs"][0]["font"]["weight"], 600)
        self.assertEqual(text["runs"][0]["lineHeight"], 20)
        self.assertEqual(parent["visualFrame"]["absoluteX"], 5)
        self.assertEqual(collect_statistics({"type": "group", "visible": True, "children": [{"type": "text", "visible": False}]}), {"totalLayers": 2, "visibleLayers": 1, "byType": {"group": 1, "text": 1}})

    def test_color_and_font_helpers_handle_edges(self) -> None:
        self.assertIsNone(color_to_json(None))
        self.assertEqual(color_to_json({"red": 2, "green": -1, "blue": 0.5, "alpha": 2, "swatchID": "SWATCH"})["hex8"], "#FF0080FF")
        self.assertEqual(font_css_family("Other Font"), "Other Font")
        self.assertIsNone(font_css_family(None))
        self.assertEqual(font_weight("Some-Black"), 900)
        self.assertEqual(font_weight("Some-Light"), 300)
        self.assertIsNone(font_weight("Unmapped"))

    def test_symbol_master_is_expanded_scaled_and_overridden(self) -> None:
        pages = self.sketch_dir / "pages"
        pages.mkdir()
        master = {
            "_class": "symbolMaster",
            "do_objectID": "MASTER",
            "symbolID": "SYMBOL",
            "name": "Button",
            "frame": {"x": 0, "y": 0, "width": 20, "height": 10},
            "layers": [{"_class": "text", "do_objectID": "TEXT", "name": "Label", "frame": {"x": 2, "y": 1, "width": 10, "height": 8}, "attributedString": {"string": "Base", "attributes": []}}],
        }
        (pages / "symbols.json").write_text(__import__("json").dumps({"layers": [master]}), encoding="utf-8")
        instance = {
            "_class": "symbolInstance",
            "do_objectID": "INSTANCE",
            "symbolID": "SYMBOL",
            "frame": {"x": 10, "y": 20, "width": 40, "height": 20},
            "overrideValues": [{"overrideName": "TEXT_stringValue", "value": "Override"}],
        }

        parsed = parse_layer(instance, self.sketch_dir)

        self.assertEqual(parsed["symbolMasterId"], "MASTER")
        self.assertEqual(parsed["children"][0]["text"]["content"], "Override")
        self.assertEqual(parsed["children"][0]["frame"]["x"], 4)
        self.assertEqual(parsed["children"][0]["frame"]["absoluteY"], 22)

    def test_parse_design_page_writes_normalized_output_and_bitmap_reference(self) -> None:
        image_path = self.sketch_dir / "images" / "asset.png"
        image_path.parent.mkdir()
        image_path.write_bytes(b"image")
        input_path = self.sketch_dir / "related.json"
        output_path = self.sketch_dir / "output" / "parsed.json"
        input_path.write_text(
            __import__("json").dumps(
                {
                    "source": {"sketchDirectory": str(self.sketch_dir), "pageFile": "page.json"},
                    "ids": {"pageID": "PAGE", "artboardID": "ARTBOARD"},
                    "artboard": {"_class": "artboard", "do_objectID": "ARTBOARD", "name": "Page", "frame": {"x": 0, "y": 0, "width": 100, "height": 80}, "backgroundColor": {"red": 1, "green": 1, "blue": 1}, "layers": [{"_class": "bitmap", "do_objectID": "IMAGE", "frame": {"x": 2, "y": 3, "width": 10, "height": 11}, "image": {"_ref": "images/asset.png"}}]},
                }
            ),
            encoding="utf-8",
        )

        result = parse_design_page(input_path, output_path)

        self.assertTrue(output_path.is_file())
        self.assertEqual(result["statistics"]["totalLayers"], 2)
        self.assertTrue(result["designPage"]["children"][0]["image"]["exists"])


if __name__ == "__main__":
    unittest.main()
