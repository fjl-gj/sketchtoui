from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.common.errors import ApiError
from app.services import mcp_design_service as design_module
from app.services.mcp_design_service import McpDesignService, compact_tree, find_node, flatten_nodes, frames_overlap, node_summary


class FakeDatabase:
    def one(self, _sql: str, _params: tuple[str, str]) -> dict[str, object] | None:
        return {
            "id": "project",
            "name": "Project",
            "filename": "source.sketch",
            "group_count": 1,
            "created_at": "created",
            "updated_at": "updated",
            "current_version_id": "version",
        }


class FakeProjects:
    def __init__(self, manifest: dict, canvas: dict) -> None:
        self.manifest = manifest
        self.canvas = canvas

    def list_projects(self, user_id: str) -> list[dict[str, str]]:
        return [{"id": "project", "userId": user_id}]

    def read_object(self, _user_id: str, _project_id: str, key: str) -> tuple[bytes, str]:
        payload = self.manifest if key == "canvas/manifest.json" else self.canvas
        return json.dumps(payload).encode("utf-8"), "application/json"


def service_fixture() -> McpDesignService:
    title = {
        "id": "title",
        "name": "Title",
        "type": "text",
        "frame": {"absoluteX": 10, "absoluteY": 10, "width": 80, "height": 20},
        "text": {"content": "Welcome", "runs": [{"lineHeight": 20, "font": {"cssFamily": "PingFang SC", "size": 14, "weight": 400}, "color": {"hex": "#111111"}}]},
        "style": {"fills": [{"enabled": True, "color": {"hex": "#FFFFFF"}}], "cornerRadii": [4], "shadows": [{"enabled": True, "color": {"hex": "#00000033"}}]},
    }
    repeated_one = {"id": "component-one", "name": "Button", "type": "group", "frame": {"absoluteX": 0, "absoluteY": 40, "width": 20, "height": 20}, "children": []}
    repeated_two = {"id": "component-two", "name": "Button", "type": "group", "frame": {"absoluteX": 30, "absoluteY": 40, "width": 20, "height": 20}, "children": []}
    artboard = {"id": "artboard", "name": "Home", "type": "artboard", "frame": {"absoluteX": 0, "absoluteY": 0, "width": 100, "height": 100}, "children": [title, repeated_one, repeated_two]}
    manifest = {"groups": [{"id": "group", "directory": "desktop", "name": "Desktop"}]}
    canvas = {"statistics": {"totalLayers": 4}, "designPages": [artboard]}
    service = McpDesignService.__new__(McpDesignService)
    service.projects = FakeProjects(manifest, canvas)
    return service


class McpDesignServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.database_patch = patch.object(design_module, "get_database", return_value=FakeDatabase())
        self.database_patch.start()
        self.service = service_fixture()

    def tearDown(self) -> None:
        self.database_patch.stop()

    def test_tree_helpers_and_overlap(self) -> None:
        node = {"id": "parent", "name": "Parent", "type": "group", "frame": {"absoluteX": 0, "absoluteY": 0, "width": 10, "height": 10}, "children": [{"id": "child", "type": "rectangle", "frame": {"absoluteX": 5, "absoluteY": 5, "width": 10, "height": 10}}]}
        summary = node_summary(node)
        compact = compact_tree(node, 0, [1])

        self.assertEqual(summary["name"], "Parent")
        self.assertEqual(compact["childCount"], 1)
        self.assertEqual(find_node([node], "child")["id"], "child")
        self.assertIsNone(find_node([node], "missing"))
        self.assertEqual(len(flatten_nodes([node])), 2)
        self.assertTrue(frames_overlap(node, node)["overlap"])
        self.assertFalse(frames_overlap(node, {"frame": {"absoluteX": 20, "absoluteY": 20, "width": 1, "height": 1}})["overlap"])

    def test_navigation_context_layer_layout_and_overlap(self) -> None:
        self.assertEqual(self.service.list_projects("user")[0]["userId"], "user")
        self.assertEqual(self.service.list_page_groups("user", "project")["groups"][0]["id"], "group")
        self.assertEqual(self.service.list_artboards("user", "project", "group")["artboards"][0]["id"], "artboard")
        context = self.service.get_artboard_context("user", "project", "group", "artboard", depth=99, max_nodes=1)
        layer = self.service.get_layer("user", "project", "group", "title")
        layout = self.service.inspect_text_layout("user", "project", "group", "title")
        overlap = self.service.check_overlap("user", "project", "group", "component-one", "component-two")

        self.assertEqual(context["statistics"]["totalLayers"], 4)
        self.assertTrue(context["truncated"])
        self.assertEqual(layer["artboardId"], "artboard")
        self.assertTrue(layout["textLayout"]["lineHeightMatchesFrame"])
        self.assertFalse(overlap["overlap"])
        with self.assertRaises(ApiError):
            self.service.get_layer("user", "project", "group", "missing")
        with self.assertRaises(ApiError):
            self.service.inspect_text_layout("user", "project", "group", "component-one")

    def test_search_tokens_components_and_resources(self) -> None:
        search = self.service.find_layers("user", "project", "welcome", limit=1)
        tokens = self.service.get_design_tokens("user", "project")
        components = self.service.list_reusable_components("user", "project")
        resource = self.service.artboard_resource("project with space", "group", "artboard")

        self.assertTrue(search["truncated"])
        self.assertEqual(search["results"][0]["id"], "title")
        self.assertIn("#111111", [item["value"] for item in tokens["colors"]])
        self.assertEqual(components["components"][0]["name"], "Button")
        self.assertIn("project%20with%20space", resource)
        self.assertEqual(self.service.get_design_context("user", resource, depth=1)["resource"], resource)
        self.assertIn("layers", self.service.layer_resource("project", "group", "layer"))
        with self.assertRaises(ApiError):
            self.service.find_layers("user", "project", " ")
        with self.assertRaises(ApiError):
            self.service.get_design_context("user", "https://invalid")
        with self.assertRaises(ApiError):
            self.service._group("user", "project", "missing")


if __name__ == "__main__":
    unittest.main()
