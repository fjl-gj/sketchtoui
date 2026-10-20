from __future__ import annotations

import sys
import unittest
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

from PIL import Image, ImageDraw


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.services.artboard_preview_service import ArtboardPreviewService


def preview_renderer() -> ArtboardPreviewService:
    renderer = ArtboardPreviewService.__new__(ArtboardPreviewService)
    renderer.fonts = {}
    renderer.images = {}
    return renderer


class ArtboardPreviewServiceTests(unittest.TestCase):
    def test_render_generates_png_from_artboard_data(self) -> None:
        renderer = preview_renderer()
        artboard = {"type": "design_page", "visible": True, "backgroundColor": {"hex": "#FFFFFF"}, "frame": {"width": 20, "height": 10, "absoluteX": 0, "absoluteY": 0}, "style": {"opacity": 1, "fills": [], "shadows": []}, "children": [{"type": "rectangle", "visible": True, "frame": {"width": 10, "height": 10, "absoluteX": 0, "absoluteY": 0}, "style": {"opacity": 1, "fills": [{"enabled": True, "color": {"hex": "#EF4444"}}], "shadows": []}}]}
        renderer.designs = SimpleNamespace(get_artboard_full=lambda *_args: ({}, {}, artboard))

        payload = renderer.render("user", "project", "group", "artboard")

        self.assertTrue(payload.startswith(b"\x89PNG"))
        self.assertEqual(Image.open(BytesIO(payload)).size, (20, 10))

    def test_image_cache_fill_gradient_and_color_helpers(self) -> None:
        renderer = preview_renderer()
        source = Image.new("RGBA", (2, 2), "#EF4444")
        renderer.projects = SimpleNamespace(read_object=lambda *_args: (self.png_bytes(source), "image/png"))
        first = renderer.image_for("user", "project", "images/a.png")
        second = renderer.image_for("user", "project", "images/a.png")
        layer = Image.new("RGBA", (20, 20), (0, 0, 0, 0))
        mask = Image.new("L", (20, 20), 0)
        ImageDraw.Draw(mask).rectangle((2, 2, 17, 17), fill=255)
        renderer.draw_image_fill(layer, mask, "user", "project", {"image": {"reference": "images/a.png"}, "patternFillType": 0, "patternTileScale": 1}, (2, 2, 18, 18))
        renderer.draw_gradient_fill(layer, mask, {"gradient": {"type": 0, "from": "{0, 0}", "to": "{1, 0}", "stops": [{"position": 0, "color": {"hex": "#000000"}}, {"position": 1, "color": {"hex": "#FFFFFF"}}]}}, (2, 2, 18, 18))

        self.assertIs(first, second)
        self.assertNotEqual(layer.getpixel((5, 5))[3], 0)
        self.assertEqual(renderer.relative_point("{0.25, 0.75}"), (0.25, 0.75))
        self.assertEqual(renderer.relative_point("bad"), (0.0, 0.0))
        self.assertEqual(renderer.color({"hex": "#01020380"}, "#FFFFFF"), (1, 2, 3, 128))
        self.assertEqual(renderer.color({"hex": "invalid"}, "#FFFFFF"), (17, 24, 39, 255))

    def test_text_masks_shadows_and_compositing_helpers(self) -> None:
        renderer = preview_renderer()
        canvas = Image.new("RGBA", (80, 40), "#FFFFFF")
        node = {"type": "text", "visible": True, "frame": {"width": 70, "height": 20, "absoluteX": 5, "absoluteY": 5}, "style": {"opacity": 1, "fills": [], "shadows": []}, "text": {"content": "ab\nCD", "runs": [{"location": 0, "length": 2, "font": {"size": 14}, "color": {"hex": "#111827"}, "lineHeight": 20, "kerning": 1, "verticalAlignment": 1, "textTransform": "uppercase", "underlineStyle": 1}, {"location": 3, "length": 2, "font": {"size": 12}, "color": {"hex": "#EF4444"}, "lineHeight": 20, "textTransform": "lowercase"}]}}
        renderer.draw_node(canvas, "user", "project", node, 0, 0, 1)
        self.assertTrue(any(pixel[:3] == (17, 24, 39) for pixel in canvas.getdata()))
        oval = renderer.node_mask((80, 40), {"type": "oval"}, (10, 10, 30, 30), {})
        path = renderer.node_mask((80, 40), {"type": "shape_path", "points": [{"point": "{0, 0}"}, {"point": "{1, 0}"}, {"point": "{0, 1}"}]}, (40, 5, 60, 25), {})
        shadow_layer = Image.new("RGBA", (80, 40), "#FFFFFF")
        renderer.apply_shadows(shadow_layer, oval, {"shadows": [{"enabled": True, "color": {"hex": "#00000080"}, "offsetX": 1, "offsetY": 1, "blurRadius": 1}]}, 1)
        blend_layer = Image.new("RGBA", (80, 40), "#FF0000")
        renderer.composite(canvas, blend_layer, 2)

        self.assertEqual(oval.getpixel((20, 20)), 255)
        self.assertEqual(path.getpixel((45, 10)), 255)
        self.assertNotEqual(shadow_layer.getpixel((21, 21))[:3], (255, 255, 255))
        self.assertEqual(renderer.transform_text("a b", "capitalize"), "A B")
        self.assertEqual(renderer.transform_text("Ab", "lowercase"), "ab")

    def test_preview_helper_branches_cover_assets_styles_and_transforms(self) -> None:
        renderer = preview_renderer()
        canvas = Image.new("RGBA", (60, 60), "#FFFFFF")
        asset = Image.new("RGBA", (4, 4), "#22C55E")
        renderer.image_for = lambda *_args: asset
        renderer.draw_node(canvas, "user", "project", {"visible": False, "frame": {"width": 10, "height": 10, "absoluteX": 0, "absoluteY": 0}}, 0, 0, 1)
        renderer.draw_node(canvas, "user", "project", {"visible": True, "frame": {"width": 0, "height": 10, "absoluteX": 0, "absoluteY": 0}}, 0, 0, 1)
        renderer.draw_node(canvas, "user", "project", {"visible": True, "frame": {"width": 10, "height": 10, "absoluteX": 100, "absoluteY": 100}}, 0, 0, 1)
        renderer.draw_node(canvas, "user", "project", {"type": "image", "visible": True, "frame": {"width": 12, "height": 12, "absoluteX": 4, "absoluteY": 4}, "image": {"reference": "images/a.png"}, "style": {"opacity": 0.5, "fills": [], "shadows": [], "blur": {"radius": 1}}}, 0, 0, 1, Image.new("L", (60, 60), 255))

        layer = Image.new("RGBA", (60, 60), (0, 0, 0, 0))
        mask = Image.new("L", (60, 60), 0)
        ImageDraw.Draw(mask).rectangle((5, 5, 25, 25), fill=255)
        renderer.draw_style(layer, mask, "user", "project", {}, (5, 5, 26, 26), {"fills": [{"enabled": True, "image": {"reference": "images/a.png"}}, {"enabled": True, "gradient": {"type": 1, "stops": [{"position": 0, "color": {"hex": "#000000"}}, {"position": 1, "color": {"hex": "#FFFFFF"}}]}}, {"enabled": True, "color": {"hex": "#EF4444"}}], "borders": [{"enabled": True, "color": {"hex": "#111827"}, "thickness": 2}]})
        renderer.draw_gradient_fill(layer, mask, {"gradient": {"stops": []}}, (5, 5, 26, 26))
        renderer.draw_image_fill(layer, mask, "user", "project", {"image": {"reference": "images/a.png"}, "patternFillType": 1}, (5, 5, 26, 26))
        renderer.draw_image(layer, "user", "project", "images/a.png", (5, 5, 15, 15))
        renderer.image_for = lambda *_args: None
        renderer.draw_image(layer, "user", "project", "missing.png", (5, 5, 15, 15))
        renderer.draw_image_fill(layer, mask, "user", "project", {"image": {"reference": "missing.png"}}, (5, 5, 15, 15))

        source = Image.new("RGBA", (60, 60), "#FFFFFF")
        red = Image.new("RGBA", (60, 60), "#FF0000")
        renderer.composite(source, red, 5)
        renderer.composite(source, red, 7)
        flip = renderer.transform_node_image(asset, (0, 0, 4, 4), {"flippedHorizontal": True, "flippedVertical": True})
        clipped_shadow = Image.new("RGBA", (60, 60), "#FFFFFF")
        renderer.apply_shadows(clipped_shadow, mask, {"shadows": [{"enabled": False}, {"enabled": True, "color": {"hex": "#00000080"}, "offsetX": 2, "offsetY": 2, "blurRadius": 0}]}, 1, mask)

        base = {"type": "rectangle", "frame": {"width": 10, "height": 10, "absoluteX": 0, "absoluteY": 0}, "style": {}, "booleanOperation": 0}
        intersect = {"type": "oval", "frame": {"width": 10, "height": 10, "absoluteX": 5, "absoluteY": 0}, "style": {}, "booleanOperation": 2}
        union = {"type": "rectangle", "frame": {"width": 10, "height": 10, "absoluteX": 15, "absoluteY": 0}, "style": {}, "booleanOperation": 0}
        difference = {"type": "rectangle", "frame": {"width": 10, "height": 10, "absoluteX": 0, "absoluteY": 0}, "style": {}, "booleanOperation": 3}
        compound = {"type": "shape_group", "children": [base, intersect, union, difference], "style": {"fills": [{"enabled": True}]}}
        self.assertIsInstance(renderer.compound_mask((60, 60), compound, 0, 0, 1), Image.Image)
        self.assertEqual(renderer.compound_mask((60, 60), {"children": []}, 0, 0, 1).getbbox(), None)
        self.assertTrue(renderer.has_composited_children({"children": [base], "rotation": 1, "style": {}}))
        self.assertTrue(renderer.has_composited_children({"children": [base], "style": {"opacity": 0.5}}))
        self.assertFalse(renderer.has_composited_children({"children": [], "style": {}}))
        self.assertEqual(renderer.shape_path([], (0, 0, 10, 10)), [])
        self.assertEqual(renderer.shape_path([{"point": "bad"}, {"point": "{1, 1}"}], (0, 0, 10, 10))[0], (0.0, 0.0))
        self.assertEqual(flip.size, (4, 4))
        self.assertNotEqual(layer.getpixel((10, 10))[3], 0)

    def test_image_for_returns_none_when_storage_fails(self) -> None:
        renderer = preview_renderer()
        renderer.projects = SimpleNamespace(read_object=lambda *_args: (_ for _ in ()).throw(RuntimeError("storage unavailable")))

        self.assertIsNone(renderer.image_for("user", "project", "missing.png"))
        self.assertIsNone(renderer.image_for("user", "project", ""))

    @staticmethod
    def png_bytes(image: Image.Image) -> bytes:
        output = BytesIO()
        image.save(output, format="PNG")
        return output.getvalue()
    def test_boolean_subtract_creates_a_cutout(self) -> None:
        renderer = preview_renderer()
        canvas = Image.new("RGBA", (120, 120), "#FFFFFF")
        base = {
            "type": "rectangle",
            "visible": True,
            "frame": {"width": 80, "height": 80, "absoluteX": 20, "absoluteY": 20},
            "style": {"opacity": 1, "fills": [], "shadows": []},
            "booleanOperation": 0,
        }
        cutout = {
            "type": "oval",
            "visible": True,
            "frame": {"width": 36, "height": 36, "absoluteX": 42, "absoluteY": 42},
            "style": {"opacity": 1, "fills": [], "shadows": []},
            "booleanOperation": 1,
        }
        group = {
            "type": "shape_group",
            "visible": True,
            "frame": {"width": 80, "height": 80, "absoluteX": 20, "absoluteY": 20},
            "style": {"opacity": 1, "fills": [{"enabled": True, "color": {"hex": "#0EA5E9"}}], "shadows": []},
            "children": [base, cutout],
        }

        renderer.draw_node(canvas, "user", "project", group, 0, 0, 1)

        self.assertEqual(canvas.getpixel((25, 25))[:3], (14, 165, 233))
        self.assertEqual(canvas.getpixel((60, 60))[:3], (255, 255, 255))

    def test_mask_chain_clips_following_siblings(self) -> None:
        renderer = preview_renderer()
        canvas = Image.new("RGBA", (120, 100), "#FFFFFF")
        common = {"visible": True, "style": {"opacity": 1, "fills": [], "shadows": []}}
        mask = {
            **common,
            "type": "oval",
            "isMask": True,
            "frame": {"width": 40, "height": 40, "absoluteX": 40, "absoluteY": 30},
        }
        child = {
            **common,
            "type": "rectangle",
            "frame": {"width": 100, "height": 80, "absoluteX": 10, "absoluteY": 10},
            "style": {"opacity": 1, "fills": [{"enabled": True, "color": {"hex": "#2563EB"}}], "shadows": []},
        }
        group = {
            **common,
            "type": "group",
            "frame": {"width": 100, "height": 80, "absoluteX": 10, "absoluteY": 10},
            "children": [mask, child],
        }

        renderer.draw_node(canvas, "user", "project", group, 0, 0, 1)

        self.assertEqual(canvas.getpixel((60, 50))[:3], (37, 99, 235))
        self.assertEqual(canvas.getpixel((15, 15))[:3], (255, 255, 255))

    def test_rotation_uses_node_frame_as_the_transform_pivot(self) -> None:
        renderer = preview_renderer()
        canvas = Image.new("RGBA", (100, 100), "#FFFFFF")
        node = {
            "type": "rectangle",
            "visible": True,
            "rotation": 90,
            "frame": {"width": 40, "height": 20, "absoluteX": 20, "absoluteY": 40},
            "style": {"opacity": 1, "fills": [{"enabled": True, "color": {"hex": "#7C3AED"}}], "shadows": []},
        }

        renderer.draw_node(canvas, "user", "project", node, 0, 0, 1)

        self.assertEqual(canvas.getpixel((40, 35))[:3], (124, 58, 237))
        self.assertEqual(canvas.getpixel((25, 50))[:3], (255, 255, 255))

    def test_rotation_is_inherited_by_group_children(self) -> None:
        renderer = preview_renderer()
        canvas = Image.new("RGBA", (100, 100), "#FFFFFF")
        child = {
            "type": "rectangle",
            "visible": True,
            "frame": {"width": 40, "height": 20, "absoluteX": 20, "absoluteY": 40},
            "style": {"opacity": 1, "fills": [{"enabled": True, "color": {"hex": "#2563EB"}}], "shadows": []},
        }
        group = {
            "type": "group",
            "visible": True,
            "rotation": 90,
            "frame": {"width": 40, "height": 20, "absoluteX": 20, "absoluteY": 40},
            "style": {"opacity": 1, "fills": [], "shadows": []},
            "children": [child],
        }

        renderer.draw_node(canvas, "user", "project", group, 0, 0, 1)

        self.assertEqual(canvas.getpixel((40, 35))[:3], (37, 99, 235))
        self.assertEqual(canvas.getpixel((25, 50))[:3], (255, 255, 255))

    def test_group_opacity_is_inherited_by_children(self) -> None:
        renderer = preview_renderer()
        canvas = Image.new("RGBA", (80, 60), "#FFFFFF")
        child = {
            "type": "rectangle",
            "visible": True,
            "frame": {"width": 40, "height": 20, "absoluteX": 20, "absoluteY": 20},
            "style": {"opacity": 1, "fills": [{"enabled": True, "color": {"hex": "#2563EB"}}], "shadows": []},
        }
        group = {
            "type": "group",
            "visible": True,
            "frame": {"width": 40, "height": 20, "absoluteX": 20, "absoluteY": 20},
            "style": {"opacity": 0.5, "fills": [], "shadows": []},
            "children": [child],
        }

        renderer.draw_node(canvas, "user", "project", group, 0, 0, 1)

        red, green, blue, _alpha = canvas.getpixel((40, 30))
        self.assertAlmostEqual(red, 146, delta=1)
        self.assertAlmostEqual(green, 177, delta=1)
        self.assertAlmostEqual(blue, 245, delta=1)


if __name__ == "__main__":
    unittest.main()
