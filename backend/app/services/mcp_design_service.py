from __future__ import annotations

import json
from collections import Counter
from typing import Any
from urllib.parse import quote, unquote, urlparse

from ..common.errors import ApiError
from ..common.extensions import get_database
from .project_import_service import ProjectImportService


MAX_CONTEXT_DEPTH = 6
MAX_CONTEXT_NODES = 1000
MAX_SEARCH_RESULTS = 100


def visual_frame(node: dict[str, Any]) -> dict[str, Any]:
    return node.get("visualFrame") or node.get("frame") or {}


def node_summary(node: dict[str, Any]) -> dict[str, Any]:
    summary = {
        "id": node.get("id"),
        "name": node.get("name") or "未命名图层",
        "type": node.get("type"),
        "sketchClass": node.get("sketchClass"),
        "visible": node.get("visible", True),
        "locked": node.get("locked", False),
        "frame": node.get("frame"),
        "visualFrame": node.get("visualFrame"),
        "rotation": node.get("rotation", 0),
    }
    if node.get("text"):
        summary["text"] = node["text"]
    if node.get("style"):
        summary["style"] = node["style"]
    if node.get("image"):
        summary["image"] = node["image"]
    return summary


def compact_tree(node: dict[str, Any], depth: int, remaining: list[int]) -> dict[str, Any]:
    remaining[0] -= 1
    result = node_summary(node)
    children = node.get("children") or []
    if depth > 0 and remaining[0] > 0 and children:
        result["children"] = [compact_tree(child, depth - 1, remaining) for child in children if remaining[0] > 0]
    elif children:
        result["childCount"] = len(children)
    return result


def find_node(nodes: list[dict[str, Any]], layer_id: str) -> dict[str, Any] | None:
    for node in nodes:
        if node.get("id") == layer_id:
            return node
        child = find_node(node.get("children") or [], layer_id)
        if child:
            return child
    return None


def flatten_nodes(nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    flattened: list[dict[str, Any]] = []
    for node in nodes:
        flattened.append(node)
        flattened.extend(flatten_nodes(node.get("children") or []))
    return flattened


def frames_overlap(first: dict[str, Any], second: dict[str, Any]) -> dict[str, Any]:
    first_frame = visual_frame(first)
    second_frame = visual_frame(second)
    left = max(float(first_frame.get("absoluteX", 0)), float(second_frame.get("absoluteX", 0)))
    top = max(float(first_frame.get("absoluteY", 0)), float(second_frame.get("absoluteY", 0)))
    right = min(
        float(first_frame.get("absoluteX", 0)) + float(first_frame.get("width", 0)),
        float(second_frame.get("absoluteX", 0)) + float(second_frame.get("width", 0)),
    )
    bottom = min(
        float(first_frame.get("absoluteY", 0)) + float(first_frame.get("height", 0)),
        float(second_frame.get("absoluteY", 0)) + float(second_frame.get("height", 0)),
    )
    width = max(0, right - left)
    height = max(0, bottom - top)
    return {"overlap": width > 0 and height > 0, "intersection": {"x": left, "y": top, "width": width, "height": height}}


class McpDesignService:
    def __init__(self) -> None:
        self.projects = ProjectImportService()

    def _project(self, user_id: str, project_id: str) -> dict[str, Any]:
        project = get_database().one(
            """SELECT id, name, filename, group_count, created_at, updated_at, status, current_version_id
               FROM projects WHERE id = ? AND user_id = ? AND status = 'ready'""",
            (project_id, user_id),
        )
        if not project:
            raise ApiError("项目不存在或无权访问", 404)
        return {
            "id": project["id"],
            "name": project["name"],
            "sourceFilename": project["filename"],
            "groupCount": project["group_count"],
            "createdAt": project["created_at"],
            "updatedAt": project["updated_at"],
            "currentVersionId": project["current_version_id"],
        }

    def list_projects(self, user_id: str) -> list[dict[str, Any]]:
        return self.projects.list_projects(user_id)

    def manifest(self, user_id: str, project_id: str) -> dict[str, Any]:
        self._project(user_id, project_id)
        payload, _content_type = self.projects.read_object(user_id, project_id, "canvas/manifest.json")
        return json.loads(payload)

    def list_page_groups(self, user_id: str, project_id: str) -> dict[str, Any]:
        project = self._project(user_id, project_id)
        manifest = self.manifest(user_id, project_id)
        return {"project": project, "groups": manifest.get("groups") or []}

    def _group(self, user_id: str, project_id: str, group_id: str) -> dict[str, Any]:
        group = next((item for item in self.manifest(user_id, project_id).get("groups") or [] if item.get("id") == group_id), None)
        if not group:
            raise ApiError("页面分组不存在", 404)
        return group

    def _canvas_data(self, user_id: str, project_id: str, group_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
        group = self._group(user_id, project_id, group_id)
        payload, _content_type = self.projects.read_object(user_id, project_id, f"canvas/{group['directory']}/canvas.json")
        return group, json.loads(payload)

    def list_artboards(self, user_id: str, project_id: str, group_id: str) -> dict[str, Any]:
        group, canvas = self._canvas_data(user_id, project_id, group_id)
        return {"group": group, "artboards": [node_summary(node) for node in canvas.get("designPages") or []]}

    def get_artboard_full(self, user_id: str, project_id: str, group_id: str, artboard_id: str) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
        project = self._project(user_id, project_id)
        group, canvas = self._canvas_data(user_id, project_id, group_id)
        artboard = next((node for node in canvas.get("designPages") or [] if node.get("id") == artboard_id), None)
        if not artboard:
            raise ApiError("设计页面不存在", 404)
        return project, group, artboard

    def get_artboard_context(
        self,
        user_id: str,
        project_id: str,
        group_id: str,
        artboard_id: str,
        depth: int = 2,
        max_nodes: int = 200,
    ) -> dict[str, Any]:
        project, group, artboard = self.get_artboard_full(user_id, project_id, group_id, artboard_id)
        _group, canvas = self._canvas_data(user_id, project_id, group_id)
        normalized_depth = max(0, min(int(depth), MAX_CONTEXT_DEPTH))
        normalized_max_nodes = max(1, min(int(max_nodes), MAX_CONTEXT_NODES))
        remaining = [normalized_max_nodes]
        return {
            "resource": self.artboard_resource(project_id, group_id, artboard_id),
            "project": project,
            "group": group,
            "artboard": compact_tree(artboard, normalized_depth, remaining),
            "statistics": canvas.get("statistics") or {},
            "truncated": remaining[0] == 0,
        }

    def find_layers(
        self,
        user_id: str,
        project_id: str,
        query: str,
        group_id: str | None = None,
        artboard_id: str | None = None,
        limit: int = 30,
    ) -> dict[str, Any]:
        phrase = query.strip().casefold()
        if not phrase:
            raise ApiError("搜索关键词不能为空")
        normalized_limit = max(1, min(int(limit), MAX_SEARCH_RESULTS))
        groups = [self._group(user_id, project_id, group_id)] if group_id else self.manifest(user_id, project_id).get("groups") or []
        results: list[dict[str, Any]] = []
        for group in groups:
            payload, _content_type = self.projects.read_object(user_id, project_id, f"canvas/{group['directory']}/canvas.json")
            canvas = json.loads(payload)
            artboards = canvas.get("designPages") or []
            if artboard_id:
                artboards = [node for node in artboards if node.get("id") == artboard_id]
            for artboard in artboards:
                for node in flatten_nodes([artboard]):
                    searchable = " ".join((str(node.get("name") or ""), str(node.get("type") or ""), str((node.get("text") or {}).get("content") or ""))).casefold()
                    if phrase in searchable:
                        result = node_summary(node)
                        result["groupId"] = group["id"]
                        result["artboardId"] = artboard.get("id")
                        result["resource"] = self.artboard_resource(project_id, group["id"], str(artboard.get("id")))
                        results.append(result)
                        if len(results) >= normalized_limit:
                            return {"query": query, "results": results, "truncated": True}
        return {"query": query, "results": results, "truncated": False}

    def get_layer(self, user_id: str, project_id: str, group_id: str, layer_id: str) -> dict[str, Any]:
        group, canvas = self._canvas_data(user_id, project_id, group_id)
        node = find_node(canvas.get("designPages") or [], layer_id)
        if not node:
            raise ApiError("图层不存在", 404)
        artboard = next((page for page in canvas.get("designPages") or [] if find_node([page], layer_id)), None)
        return {
            "project": self._project(user_id, project_id),
            "group": group,
            "artboardId": artboard.get("id") if artboard else None,
            "resource": self.layer_resource(project_id, group_id, layer_id),
            "layer": node_summary(node),
        }

    def inspect_text_layout(self, user_id: str, project_id: str, group_id: str, layer_id: str) -> dict[str, Any]:
        result = self.get_layer(user_id, project_id, group_id, layer_id)
        layer = result["layer"]
        if layer.get("type") != "text":
            raise ApiError("目标图层不是文本图层")
        frame = layer.get("visualFrame") or layer.get("frame") or {}
        runs = (layer.get("text") or {}).get("runs") or []
        result["textLayout"] = {
            "content": (layer.get("text") or {}).get("content", ""),
            "frame": frame,
            "runs": runs,
            "lineHeightMatchesFrame": all(run.get("lineHeight") == frame.get("height") for run in runs),
        }
        return result

    def check_overlap(self, user_id: str, project_id: str, group_id: str, first_layer_id: str, second_layer_id: str) -> dict[str, Any]:
        _group, canvas = self._canvas_data(user_id, project_id, group_id)
        first = find_node(canvas.get("designPages") or [], first_layer_id)
        second = find_node(canvas.get("designPages") or [], second_layer_id)
        if not first or not second:
            raise ApiError("至少有一个图层不存在", 404)
        return {"first": node_summary(first), "second": node_summary(second), **frames_overlap(first, second)}

    def get_design_tokens(self, user_id: str, project_id: str, group_id: str | None = None) -> dict[str, Any]:
        project = self._project(user_id, project_id)
        groups = [self._group(user_id, project_id, group_id)] if group_id else self.manifest(user_id, project_id).get("groups") or []
        colors: Counter[str] = Counter()
        typography: Counter[tuple[str, int | float | None, int | float | None, int | float | None]] = Counter()
        radii: Counter[float] = Counter()
        shadows: Counter[str] = Counter()
        for group in groups:
            _group, canvas = self._canvas_data(user_id, project_id, group["id"])
            for node in flatten_nodes(canvas.get("designPages") or []):
                style = node.get("style") or {}
                for item in [*(style.get("fills") or []), *(style.get("borders") or [])]:
                    if item.get("enabled", True) and item.get("color", {}).get("hex"):
                        colors[str(item["color"]["hex"]).upper()] += 1
                for radius in style.get("cornerRadii") or []:
                    if isinstance(radius, (int, float)):
                        radii[float(radius)] += 1
                for shadow in style.get("shadows") or []:
                    if shadow.get("enabled", True):
                        shadows[json.dumps(shadow, ensure_ascii=False, sort_keys=True)] += 1
                for run in (node.get("text") or {}).get("runs") or []:
                    font = run.get("font") or {}
                    color = run.get("color") or {}
                    if color.get("hex"):
                        colors[str(color["hex"]).upper()] += 1
                    typography[(str(font.get("cssFamily") or font.get("name") or "sans-serif"), font.get("size"), font.get("weight"), run.get("lineHeight"))] += 1
        return {
            "project": project,
            "groupId": group_id,
            "colors": [{"value": value, "usageCount": count} for value, count in colors.most_common(80)],
            "typography": [
                {"fontFamily": family, "fontSize": size, "fontWeight": weight, "lineHeight": line_height, "usageCount": count}
                for (family, size, weight, line_height), count in typography.most_common(80)
            ],
            "cornerRadii": [{"value": value, "usageCount": count} for value, count in radii.most_common(40)],
            "shadows": [{"value": json.loads(value), "usageCount": count} for value, count in shadows.most_common(40)],
        }

    def list_reusable_components(self, user_id: str, project_id: str, group_id: str | None = None) -> dict[str, Any]:
        project = self._project(user_id, project_id)
        groups = [self._group(user_id, project_id, group_id)] if group_id else self.manifest(user_id, project_id).get("groups") or []
        candidates: dict[tuple[str, str], list[dict[str, Any]]] = {}
        for group in groups:
            _group, canvas = self._canvas_data(user_id, project_id, group["id"])
            for artboard in canvas.get("designPages") or []:
                for node in flatten_nodes([artboard]):
                    name = str(node.get("name") or "").strip()
                    node_type = str(node.get("type") or "")
                    if not name or node_type not in {"group", "shape_group", "symbol_instance", "symbol_master"}:
                        continue
                    candidates.setdefault((name, node_type), []).append(
                        {
                            "id": node.get("id"),
                            "groupId": group["id"],
                            "artboardId": artboard.get("id"),
                            "childCount": len(node.get("children") or []),
                        }
                    )
        components = [
            {"name": name, "type": node_type, "occurrenceCount": len(items), "instances": items[:20], "truncated": len(items) > 20}
            for (name, node_type), items in candidates.items()
            if len(items) > 1 or node_type.startswith("symbol_")
        ]
        components.sort(key=lambda item: (-item["occurrenceCount"], item["name"]))
        return {"project": project, "groupId": group_id, "components": components[:100], "truncated": len(components) > 100}

    def get_design_context(self, user_id: str, resource: str, depth: int = 2, max_nodes: int = 200) -> dict[str, Any]:
        parsed = urlparse(resource)
        parts = [unquote(parsed.netloc), *[unquote(part) for part in parsed.path.split("/") if part]]
        if parsed.scheme != "sketchtoui" or len(parts) != 6 or parts[0] != "projects" or parts[2] != "groups" or parts[4] != "artboards":
            raise ApiError("资源链接格式无效，应为 sketchtoui://projects/{projectId}/groups/{groupId}/artboards/{artboardId}")
        return self.get_artboard_context(user_id, parts[1], parts[3], parts[5], depth, max_nodes)

    @staticmethod
    def artboard_resource(project_id: str, group_id: str, artboard_id: str) -> str:
        return f"sketchtoui://projects/{quote(project_id, safe='')}/groups/{quote(group_id, safe='')}/artboards/{quote(artboard_id, safe='')}"

    @staticmethod
    def layer_resource(project_id: str, group_id: str, layer_id: str) -> str:
        return f"sketchtoui://projects/{quote(project_id, safe='')}/groups/{quote(group_id, safe='')}/layers/{quote(layer_id, safe='')}"
