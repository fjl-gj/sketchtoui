from __future__ import annotations

from io import BytesIO
from pathlib import Path
from typing import Any

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

from ..config.settings import settings
from .mcp_design_service import McpDesignService, visual_frame
from .project_import_service import ProjectImportService


class ArtboardPreviewService:
    """Raster preview renderer for MCP resources and the project canvas."""

    def __init__(self) -> None:
        self.designs = McpDesignService()
        self.projects = ProjectImportService()
        self.fonts: dict[int, ImageFont.ImageFont] = {}
        self.images: dict[tuple[str, str, str], Image.Image] = {}

    def render(self, user_id: str, project_id: str, group_id: str, artboard_id: str) -> bytes:
        _project, _group, artboard = self.designs.get_artboard_full(user_id, project_id, group_id, artboard_id)
        frame = visual_frame(artboard)
        source_width = max(1, int(round(float(frame.get("width") or 1))))
        source_height = max(1, int(round(float(frame.get("height") or 1))))
        limit = max(320, settings.mcp_preview_max_dimension)
        scale = min(1.0, limit / max(source_width, source_height))
        width = max(1, int(round(source_width * scale)))
        height = max(1, int(round(source_height * scale)))
        image = Image.new("RGBA", (width, height), self.color(artboard.get("backgroundColor"), "#FFFFFF"))
        origin_x = float(frame.get("absoluteX") or 0)
        origin_y = float(frame.get("absoluteY") or 0)
        self.draw_node(image, user_id, project_id, artboard, origin_x, origin_y, scale)
        output = BytesIO()
        image.convert("RGB").save(output, format="PNG", optimize=True)
        return output.getvalue()

    def draw_node(
        self,
        image: Image.Image,
        user_id: str,
        project_id: str,
        node: dict[str, Any],
        origin_x: float,
        origin_y: float,
        scale: float,
        clip_mask: Image.Image | None = None,
    ) -> None:
        if node.get("visible", True) is False:
            return
        frame = node.get("frame") or visual_frame(node)
        source_width = float(frame.get("width") or 0)
        source_height = float(frame.get("height") or 0)
        if source_width <= 0 or source_height <= 0:
            return
        x = (float(frame.get("absoluteX") or 0) - origin_x) * scale
        y = (float(frame.get("absoluteY") or 0) - origin_y) * scale
        right = x + source_width * scale
        bottom = y + source_height * scale
        if right < 0 or bottom < 0 or x > image.width or y > image.height:
            return

        bounds = tuple(int(round(value)) for value in (x, y, right, bottom))
        style = node.get("style") or {}
        if self.has_composited_children(node):
            self.draw_composited_container(image, user_id, project_id, node, origin_x, origin_y, scale, bounds, clip_mask)
            return
        mask = self.node_mask(image.size, node, bounds, style, origin_x, origin_y, scale)
        layer = Image.new("RGBA", image.size, (0, 0, 0, 0))
        self.draw_style(layer, mask, user_id, project_id, node, bounds, style)
        if node.get("type") == "image" and (node.get("image") or {}).get("reference"):
            self.draw_image(layer, user_id, project_id, str(node["image"]["reference"]), bounds, mask)
        if node.get("type") == "text":
            self.draw_text(layer, node, bounds, scale)

        mask = self.transform_node_image(mask, bounds, node)
        layer = self.transform_node_image(layer, bounds, node)
        opacity = max(0.0, min(1.0, float(style.get("opacity", 1) or 0)))
        if opacity < 1:
            layer.putalpha(layer.getchannel("A").point(lambda value: int(value * opacity)))
        blur = style.get("blur") or {}
        radius = max(0.0, float(blur.get("radius") or 0) * scale)
        if radius:
            layer = layer.filter(ImageFilter.GaussianBlur(radius))
        if clip_mask is not None:
            layer.putalpha(ImageChops.multiply(layer.getchannel("A"), clip_mask))
        self.apply_shadows(image, mask, style, scale, clip_mask)
        self.composite(image, layer, int(style.get("blendMode") or 0))
        active_mask: Image.Image | None = None
        for child in node.get("children") or []:
            if child.get("breaksMaskChain"):
                active_mask = None
            child_mask = clip_mask
            if active_mask is not None:
                child_mask = ImageChops.multiply(child_mask, active_mask) if child_mask is not None else active_mask
            self.draw_node(image, user_id, project_id, child, origin_x, origin_y, scale, child_mask)
            if child.get("isMask"):
                active_mask = self.clip_mask_for_node(image.size, child, origin_x, origin_y, scale)

    @staticmethod
    def has_composited_children(node: dict[str, Any]) -> bool:
        if not node.get("children"):
            return False
        style = node.get("style") or {}
        return bool(
            node.get("rotation")
            or node.get("flippedHorizontal")
            or node.get("flippedVertical")
            or float(style.get("opacity", 1) or 0) < 1
            or float((style.get("blur") or {}).get("radius") or 0) > 0
            or int(style.get("blendMode") or 0) != 0
        )

    def draw_composited_container(
        self,
        image: Image.Image,
        user_id: str,
        project_id: str,
        node: dict[str, Any],
        origin_x: float,
        origin_y: float,
        scale: float,
        bounds: tuple[int, int, int, int],
        clip_mask: Image.Image | None,
    ) -> None:
        style = node.get("style") or {}
        flattened_style = {**style, "opacity": 1, "blendMode": 0, "blur": None}
        flattened = {
            **node,
            "style": flattened_style,
            "rotation": 0,
            "flippedHorizontal": False,
            "flippedVertical": False,
        }
        surface = Image.new("RGBA", image.size, (0, 0, 0, 0))
        self.draw_node(surface, user_id, project_id, flattened, origin_x, origin_y, scale)
        surface = self.transform_node_image(surface, bounds, node)
        opacity = max(0.0, min(1.0, float(style.get("opacity", 1) or 0)))
        if opacity < 1:
            surface.putalpha(surface.getchannel("A").point(lambda value: int(value * opacity)))
        blur = style.get("blur") or {}
        radius = max(0.0, float(blur.get("radius") or 0) * scale)
        if radius:
            surface = surface.filter(ImageFilter.GaussianBlur(radius))
        if clip_mask is not None:
            surface.putalpha(ImageChops.multiply(surface.getchannel("A"), clip_mask))
        self.composite(image, surface, int(style.get("blendMode") or 0))

    def draw_style(
        self,
        layer: Image.Image,
        mask: Image.Image,
        user_id: str,
        project_id: str,
        node: dict[str, Any],
        bounds: tuple[int, int, int, int],
        style: dict[str, Any],
    ) -> None:
        for fill in (item for item in style.get("fills") or [] if item.get("enabled", True)):
            if (fill.get("image") or {}).get("reference"):
                self.draw_image_fill(layer, mask, user_id, project_id, fill, bounds)
            elif fill.get("gradient"):
                self.draw_gradient_fill(layer, mask, fill, bounds)
            elif fill.get("color"):
                color = self.color(fill.get("color"), "#00000000")
                opacity = max(0.0, min(1.0, float(fill.get("opacity", 1) or 0)))
                layer.paste((*color[:3], int(color[3] * opacity)), mask=mask)
        border = next((item for item in style.get("borders") or [] if item.get("enabled", True) and item.get("color")), None)
        if border:
            thickness = max(1, int(round(float(border.get("thickness") or 1))))
            border_mask = mask.filter(ImageFilter.MaxFilter(thickness * 2 + 1))
            outline = ImageChops.subtract(border_mask, mask)
            layer.paste(self.color(border.get("color"), "#111827"), mask=outline)

    def draw_gradient_fill(self, layer: Image.Image, mask: Image.Image, fill: dict[str, Any], bounds: tuple[int, int, int, int]) -> None:
        gradient = fill.get("gradient") or {}
        stops = [item for item in gradient.get("stops") or [] if item.get("color")]
        if not stops:
            return
        stops.sort(key=lambda item: float(item.get("position") or 0))
        width = max(1, bounds[2] - bounds[0])
        height = max(1, bounds[3] - bounds[1])
        ramp = Image.radial_gradient("L") if gradient.get("type") == 1 else Image.linear_gradient("L")
        if gradient.get("type") != 1:
            from_x, from_y = self.relative_point(gradient.get("from"))
            to_x, to_y = self.relative_point(gradient.get("to"))
            if abs(to_x - from_x) >= abs(to_y - from_y):
                ramp = ramp.rotate(90, expand=True)
        ramp = ramp.resize((width, height), Image.Resampling.BILINEAR)
        channels = []
        for channel in range(4):
            lookup = []
            for value in range(256):
                position = value / 255
                before = max((item for item in stops if float(item.get("position") or 0) <= position), key=lambda item: float(item.get("position") or 0), default=stops[0])
                after = min((item for item in stops if float(item.get("position") or 0) >= position), key=lambda item: float(item.get("position") or 0), default=stops[-1])
                before_position = float(before.get("position") or 0)
                after_position = float(after.get("position") or 0)
                ratio = 0 if after_position == before_position else (position - before_position) / (after_position - before_position)
                start = self.color(before.get("color"), "#00000000")[channel]
                end = self.color(after.get("color"), "#00000000")[channel]
                lookup.append(int(round(start + (end - start) * ratio)))
            channels.append(ramp.point(lookup))
        content = Image.merge("RGBA", tuple(channels))
        opacity = max(0.0, min(1.0, float(fill.get("opacity", 1) or 0)))
        if opacity < 1:
            content.putalpha(content.getchannel("A").point(lambda value: int(value * opacity)))
        full_size = Image.new("RGBA", layer.size, (0, 0, 0, 0))
        full_size.alpha_composite(content, (bounds[0], bounds[1]))
        layer.alpha_composite(Image.composite(full_size, Image.new("RGBA", layer.size), mask))

    @staticmethod
    def relative_point(value: str | None) -> tuple[float, float]:
        raw = str(value or "{0, 0}").strip("{} ").split(",")
        try:
            return float(raw[0]), float(raw[1])
        except (IndexError, ValueError):
            return 0.0, 0.0

    def draw_image_fill(
        self,
        layer: Image.Image,
        mask: Image.Image,
        user_id: str,
        project_id: str,
        fill: dict[str, Any],
        bounds: tuple[int, int, int, int],
    ) -> None:
        reference = str((fill.get("image") or {}).get("reference") or "")
        source = self.image_for(user_id, project_id, reference)
        if source is None:
            return
        width = max(1, bounds[2] - bounds[0])
        height = max(1, bounds[3] - bounds[1])
        content = Image.new("RGBA", layer.size, (0, 0, 0, 0))
        if fill.get("patternFillType") == 0:
            tile_scale = max(0.01, float(fill.get("patternTileScale") or 1))
            tile = source.resize((max(1, int(source.width * tile_scale)), max(1, int(source.height * tile_scale))), Image.Resampling.LANCZOS)
            for tile_y in range(bounds[1], bounds[3], tile.height):
                for tile_x in range(bounds[0], bounds[2], tile.width):
                    content.alpha_composite(tile, (tile_x, tile_y))
        else:
            content.alpha_composite(source.resize((width, height), Image.Resampling.LANCZOS), (bounds[0], bounds[1]))
        layer.alpha_composite(Image.composite(content, Image.new("RGBA", layer.size), mask))

    def draw_image(
        self,
        canvas: Image.Image,
        user_id: str,
        project_id: str,
        reference: str,
        bounds: tuple[int, int, int, int],
        mask: Image.Image | None = None,
    ) -> None:
        source = self.image_for(user_id, project_id, reference)
        if source is None:
            return
        width = max(1, bounds[2] - bounds[0])
        height = max(1, bounds[3] - bounds[1])
        content = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
        content.alpha_composite(source.resize((width, height), Image.Resampling.LANCZOS), (bounds[0], bounds[1]))
        canvas.alpha_composite(Image.composite(content, Image.new("RGBA", canvas.size), mask) if mask else content)

    def image_for(self, user_id: str, project_id: str, reference: str) -> Image.Image | None:
        if not reference:
            return None
        key = (user_id, project_id, reference)
        source = self.images.get(key)
        if source is not None:
            return source
        try:
            payload, _content_type = self.projects.read_object(user_id, project_id, f"sketch/{reference}")
            source = Image.open(BytesIO(payload)).convert("RGBA")
            self.images[key] = source
            return source
        except Exception:
            return None

    def draw_text(self, canvas: Image.Image, node: dict[str, Any], bounds: tuple[int, int, int, int], scale: float) -> None:
        text_data = node.get("text") or {}
        content = str(text_data.get("content") or "")
        if not content:
            return
        runs = text_data.get("runs") or [{}]
        default_run = runs[0]
        font_size = max(8, int(round(float((default_run.get("font") or {}).get("size") or 14) * scale)))
        line_height = max(font_size, int(round(float(default_run.get("lineHeight") or font_size / scale * 1.25) * scale)))
        lines = content.split("\n")
        block_height = line_height * len(lines)
        alignment = int(default_run.get("alignment") or 0)
        vertical_alignment = int(default_run.get("verticalAlignment") or 0)
        y = bounds[1] + ((bounds[3] - bounds[1] - block_height) // 2 if vertical_alignment == 1 else max(0, bounds[3] - bounds[1] - block_height) if vertical_alignment == 2 else 0)
        draw = ImageDraw.Draw(canvas)
        offset = 0
        for line in lines:
            segments = self.text_segments(content, offset, offset + len(line), runs)
            widths = [self.text_width(segment[0], segment[1], scale) for segment in segments]
            total_width = sum(widths)
            x = bounds[0] + ((bounds[2] - bounds[0] - total_width) // 2 if alignment == 1 else max(0, bounds[2] - bounds[0] - total_width) if alignment == 2 else 0)
            for (segment, run), segment_width in zip(segments, widths):
                font_data = run.get("font") or {}
                size = max(8, int(round(float(font_data.get("size") or 14) * scale)))
                font = self.font(size)
                segment = self.transform_text(segment, run.get("textTransform"))
                ascent, descent = font.getmetrics()
                baseline = y + max(0, (line_height - ascent - descent) // 2) + ascent
                self.draw_text_run(draw, segment, x, baseline, font, self.color(run.get("color"), "#111827"), float(run.get("kerning") or 0) * scale)
                if run.get("underlineStyle"):
                    draw.line((x, baseline + 1, x + segment_width, baseline + 1), fill=self.color(run.get("color"), "#111827"), width=max(1, int(round(scale))))
                x += segment_width
            y += line_height
            offset += len(line) + 1

    def text_segments(self, content: str, start: int, end: int, runs: list[dict[str, Any]]) -> list[tuple[str, dict[str, Any]]]:
        segments: list[tuple[str, dict[str, Any]]] = []
        for run in runs:
            run_start = max(start, int(run.get("location") or 0))
            run_end = min(end, int(run.get("location") or 0) + int(run.get("length") or len(content)))
            if run_end > run_start:
                segments.append((content[run_start:run_end], run))
        return segments or [(content[start:end], runs[0] if runs else {})]

    def text_width(self, text: str, run: dict[str, Any], scale: float) -> int:
        font_data = run.get("font") or {}
        font = self.font(max(8, int(round(float(font_data.get("size") or 14) * scale))))
        kerning = float(run.get("kerning") or 0) * scale
        text = self.transform_text(text, run.get("textTransform"))
        return int(round(font.getlength(text) + max(0, len(text) - 1) * kerning))

    @staticmethod
    def transform_text(text: str, transform: Any) -> str:
        if not isinstance(transform, str):
            return text
        if transform.lower() == "uppercase":
            return text.upper()
        if transform.lower() == "lowercase":
            return text.lower()
        if transform.lower() == "capitalize":
            return " ".join(item.capitalize() for item in text.split(" "))
        return text

    @staticmethod
    def draw_text_run(draw: ImageDraw.ImageDraw, text: str, x: int, baseline: int, font: ImageFont.ImageFont, color: tuple[int, int, int, int], kerning: float) -> None:
        if not kerning:
            draw.text((x, baseline), text, font=font, fill=color, anchor="ls")
            return
        cursor = x
        for character in text:
            draw.text((cursor, baseline), character, font=font, fill=color, anchor="ls")
            cursor += font.getlength(character) + kerning

    def node_mask(
        self,
        size: tuple[int, int],
        node: dict[str, Any],
        bounds: tuple[int, int, int, int],
        style: dict[str, Any],
        origin_x: float | None = None,
        origin_y: float | None = None,
        scale: float = 1,
    ) -> Image.Image:
        if self.is_compound_shape_group(node, style) and origin_x is not None and origin_y is not None:
            return self.compound_mask(size, node, origin_x, origin_y, scale)
        mask = Image.new("L", size, 0)
        draw = ImageDraw.Draw(mask)
        if node.get("type") == "oval":
            draw.ellipse(bounds, fill=255)
        elif node.get("type") == "shape_path" and node.get("points"):
            points = self.shape_path(node.get("points") or [], bounds)
            if len(points) >= 3:
                draw.polygon(points, fill=255)
        else:
            radii = style.get("cornerRadii") or []
            radius = max(0, int(round(float(radii[0] if radii else 0))))
            draw.rounded_rectangle(bounds, radius=radius, fill=255)
        return mask

    @staticmethod
    def is_compound_shape_group(node: dict[str, Any], style: dict[str, Any]) -> bool:
        children = node.get("children") or []
        has_paint = any(item.get("enabled", True) for item in style.get("fills") or []) or any(item.get("enabled", True) for item in style.get("borders") or [])
        return node.get("type") == "shape_group" and has_paint and bool(children) and all(child.get("type") in {"shape_path", "rectangle", "oval"} for child in children)

    def compound_mask(self, size: tuple[int, int], node: dict[str, Any], origin_x: float, origin_y: float, scale: float) -> Image.Image:
        children = node.get("children") or []
        if not children:
            return Image.new("L", size, 0)
        result = self.clip_mask_for_node(size, children[0], origin_x, origin_y, scale)
        for child in children[1:]:
            operand = self.clip_mask_for_node(size, child, origin_x, origin_y, scale)
            operation = int(child.get("booleanOperation") if child.get("booleanOperation") is not None else 0)
            if operation == 1:
                result = ImageChops.subtract(result, operand)
            elif operation == 2:
                result = ImageChops.multiply(result, operand)
            elif operation == 3:
                result = ImageChops.difference(result, operand)
            else:
                result = ImageChops.lighter(result, operand)
        return result

    def clip_mask_for_node(self, size: tuple[int, int], node: dict[str, Any], origin_x: float, origin_y: float, scale: float) -> Image.Image:
        frame = node.get("frame") or visual_frame(node)
        x = (float(frame.get("absoluteX") or 0) - origin_x) * scale
        y = (float(frame.get("absoluteY") or 0) - origin_y) * scale
        right = x + float(frame.get("width") or 0) * scale
        bottom = y + float(frame.get("height") or 0) * scale
        bounds = tuple(int(round(value)) for value in (x, y, right, bottom))
        return self.transform_node_image(self.node_mask(size, node, bounds, node.get("style") or {}, origin_x, origin_y, scale), bounds, node)

    @staticmethod
    def transform_node_image(image: Image.Image, bounds: tuple[int, int, int, int], node: dict[str, Any]) -> Image.Image:
        transformed = image
        if node.get("flippedHorizontal") or node.get("flippedVertical"):
            crop = transformed.crop(bounds)
            if node.get("flippedHorizontal"):
                crop = crop.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
            if node.get("flippedVertical"):
                crop = crop.transpose(Image.Transpose.FLIP_TOP_BOTTOM)
            transformed = Image.new(image.mode, image.size, 0)
            transformed.paste(crop, (bounds[0], bounds[1]))
        rotation = float(node.get("rotation") or 0)
        if rotation:
            center = ((bounds[0] + bounds[2]) / 2, (bounds[1] + bounds[3]) / 2)
            transformed = transformed.rotate(-rotation, resample=Image.Resampling.BICUBIC, center=center)
        return transformed

    def shape_path(self, source_points: list[dict[str, Any]], bounds: tuple[int, int, int, int]) -> list[tuple[float, float]]:
        if len(source_points) < 2:
            return []
        width = bounds[2] - bounds[0]
        height = bounds[3] - bounds[1]

        def point(value: str | None) -> tuple[float, float]:
            raw = str(value or "{0, 0}").strip("{} ").split(",")
            try:
                return bounds[0] + float(raw[0]) * width, bounds[1] + float(raw[1]) * height
            except (IndexError, ValueError):
                return float(bounds[0]), float(bounds[1])

        output = [point(source_points[0].get("point"))]
        loop = source_points[1:] + source_points[:1]
        previous = source_points[0]
        for current in loop:
            start = point(previous.get("point"))
            end = point(current.get("point"))
            curved = previous.get("hasCurveFrom") or current.get("hasCurveTo") or previous.get("curveMode") == 2 or current.get("curveMode") == 2
            if curved:
                control_one = point(previous.get("curveFrom") or previous.get("point"))
                control_two = point(current.get("curveTo") or current.get("point"))
                for step in range(1, 13):
                    t = step / 12
                    inverse = 1 - t
                    output.append((
                        inverse ** 3 * start[0] + 3 * inverse ** 2 * t * control_one[0] + 3 * inverse * t ** 2 * control_two[0] + t ** 3 * end[0],
                        inverse ** 3 * start[1] + 3 * inverse ** 2 * t * control_one[1] + 3 * inverse * t ** 2 * control_two[1] + t ** 3 * end[1],
                    ))
            else:
                output.append(end)
            previous = current
        return output

    def apply_shadows(self, image: Image.Image, mask: Image.Image, style: dict[str, Any], scale: float, clip_mask: Image.Image | None = None) -> None:
        for shadow in style.get("shadows") or []:
            if not shadow.get("enabled", True):
                continue
            color = self.color(shadow.get("color"), "#00000033")
            blur = max(0.0, float(shadow.get("blurRadius") or 0) * scale)
            offset_x = int(round(float(shadow.get("offsetX") or 0) * scale))
            offset_y = int(round(float(shadow.get("offsetY") or 0) * scale))
            shadow_mask = mask.filter(ImageFilter.GaussianBlur(blur)) if blur else mask
            shifted = Image.new("L", image.size, 0)
            shifted.paste(shadow_mask, (offset_x, offset_y))
            if clip_mask is not None:
                shifted = ImageChops.multiply(shifted, clip_mask)
            image.paste(color, mask=shifted)

    @staticmethod
    def composite(destination: Image.Image, layer: Image.Image, blend_mode: int) -> None:
        alpha = layer.getchannel("A")
        if blend_mode == 2:
            destination.paste(ImageChops.multiply(destination, layer), mask=alpha)
        elif blend_mode == 5:
            destination.paste(ImageChops.screen(destination, layer), mask=alpha)
        elif blend_mode == 7 and hasattr(ImageChops, "overlay"):
            destination.paste(ImageChops.overlay(destination, layer), mask=alpha)
        else:
            destination.alpha_composite(layer)

    def font(self, size: int) -> ImageFont.ImageFont:
        if size in self.fonts:
            return self.fonts[size]
        candidates = [settings.mcp_preview_font_path, "C:/Windows/Fonts/msyh.ttc", "C:/Windows/Fonts/msyh.ttf"]
        for candidate in candidates:
            if candidate and Path(candidate).is_file():
                try:
                    font = ImageFont.truetype(candidate, size)
                    self.fonts[size] = font
                    return font
                except OSError:
                    continue
        font = ImageFont.load_default(size=size)
        self.fonts[size] = font
        return font

    @staticmethod
    def color(value: dict[str, Any] | None, fallback: str) -> tuple[int, int, int, int]:
        if not value:
            value = {"hex": fallback}
        hex_value = str(value.get("hex") or fallback).lstrip("#")
        if len(hex_value) in {6, 8}:
            try:
                red = int(hex_value[0:2], 16)
                green = int(hex_value[2:4], 16)
                blue = int(hex_value[4:6], 16)
                alpha = int(hex_value[6:8], 16) if len(hex_value) == 8 else int(round(float(value.get("alpha", 1)) * 255))
                return red, green, blue, max(0, min(255, alpha))
            except ValueError:
                pass
        return 17, 24, 39, 255
