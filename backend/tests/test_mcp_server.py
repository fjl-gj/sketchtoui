from __future__ import annotations

import asyncio
import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.mcp import server as mcp_server


class FakeApp:
    def __init__(self) -> None:
        self.middleware: list[tuple[object, dict]] = []

    def add_middleware(self, middleware: object, **kwargs: object) -> None:
        self.middleware.append((middleware, kwargs))


class FakeFastMCP:
    instance: "FakeFastMCP | None" = None

    def __init__(self, *_args: object, **kwargs: object) -> None:
        self.kwargs = kwargs
        self.tools: dict[str, object] = {}
        self.resources: dict[str, object] = {}
        self.prompts: dict[str, object] = {}
        self.routes: dict[str, object] = {}
        self.app = FakeApp()
        FakeFastMCP.instance = self

    def tool(self):
        return lambda function: self.tools.setdefault(function.__name__, function) or function

    def resource(self, uri: str, **_kwargs: object):
        return lambda function: self.resources.setdefault(uri, function) or function

    def prompt(self, **_kwargs: object):
        return lambda function: self.prompts.setdefault(function.__name__, function) or function

    def custom_route(self, path: str, **_kwargs: object):
        return lambda function: self.routes.setdefault(path, function) or function

    def streamable_http_app(self) -> FakeApp:
        return self.app


class McpServerTests(unittest.TestCase):
    def test_token_verifier_and_current_user(self) -> None:
        service = Mock()
        service.authenticate.return_value = {"id": "token", "scopes": ["design:read"], "user_id": "user", "username": "name", "name": "local"}
        token = asyncio.run(mcp_server.SketchToUiTokenVerifier(service).verify_token("skt_token"))
        self.assertEqual(token.subject, "user")
        service.authenticate.return_value = None
        self.assertIsNone(asyncio.run(mcp_server.SketchToUiTokenVerifier(service).verify_token("bad")))
        with patch.object(mcp_server, "get_access_token", return_value=SimpleNamespace(subject="user")):
            self.assertEqual(mcp_server.current_user_id(), "user")
        with patch.object(mcp_server, "get_access_token", return_value=None), self.assertRaises(PermissionError):
            mcp_server.current_user_id()

    def test_remote_mcp_tools_resources_and_prompt(self) -> None:
        design = Mock()
        design.list_projects.return_value = [{"id": "project"}]
        design.list_page_groups.return_value = {"groups": []}
        design.list_artboards.return_value = {"artboards": []}
        design.get_design_context.return_value = {"context": True}
        design.get_artboard_context.return_value = {"context": True}
        design.find_layers.return_value = {"layers": []}
        design.get_layer.return_value = {"id": "layer"}
        design.inspect_text_layout.return_value = {"alignment": "left"}
        design.check_overlap.return_value = {"overlap": False}
        design.get_design_tokens.return_value = {"colors": []}
        design.list_reusable_components.return_value = {"components": []}
        preview = Mock()
        preview.render.return_value = b"png"
        project = Mock()
        project.read_object.return_value = (b"image", "image/png")
        token = Mock()
        with patch.object(mcp_server, "FastMCP", FakeFastMCP), patch.object(mcp_server, "McpTokenService", return_value=token), patch.object(mcp_server, "McpDesignService", return_value=design), patch.object(mcp_server, "ArtboardPreviewService", return_value=preview), patch.object(mcp_server, "ProjectImportService", return_value=project), patch.object(mcp_server, "Image", side_effect=lambda **kwargs: kwargs), patch.object(mcp_server, "get_access_token", return_value=SimpleNamespace(subject="user")):
            application = mcp_server.create_mcp_app()

        fake = FakeFastMCP.instance
        self.assertIs(application, fake.app)
        self.assertEqual(len(fake.tools), 12)
        with patch.object(mcp_server, "current_user_id", return_value="user"):
            self.assertEqual(fake.tools["list_projects"]()["projects"][0]["id"], "project")
            fake.tools["list_page_groups"]("project")
            fake.tools["list_artboards"]("project", "group")
            fake.tools["get_design_context"]("sketchtoui://projects/project")
            fake.tools["find_layers"]("project", "text", "group", "artboard", 2)
            self.assertEqual(fake.tools["get_layer"]("project", "group", "layer")["id"], "layer")
            fake.tools["inspect_text_layout"]("project", "group", "layer")
            fake.tools["check_overlap"]("project", "group", "first", "second")
            fake.tools["get_design_tokens"]("project", "group")
            fake.tools["list_reusable_components"]("project", "group")
            self.assertEqual(getattr(fake.tools["get_artboard_preview"]("project", "group", "artboard"), "data", b"png"), b"png")
            self.assertEqual(getattr(fake.tools["get_design_asset"]("project", "images/icon.png"), "format", "png"), "png")
            project.read_object.return_value = (b"text", "text/plain")
            with self.assertRaises(ValueError):
                fake.tools["get_design_asset"]("project", "document.json")

            projects = json.loads(fake.resources["sketchtoui://projects"]())
            self.assertEqual(projects["projects"][0]["id"], "project")
            self.assertEqual(json.loads(fake.resources["sketchtoui://projects/{project_id}"]("project")), {"groups": []})
            self.assertEqual(json.loads(fake.resources["sketchtoui://projects/{project_id}/groups/{group_id}"]("project", "group")), {"artboards": []})
            self.assertEqual(json.loads(fake.resources["sketchtoui://projects/{project_id}/groups/{group_id}/artboards/{artboard_id}"]("project", "group", "artboard")), {"context": True})
            self.assertEqual(json.loads(fake.resources["sketchtoui://projects/{project_id}/groups/{group_id}/layers/{layer_id}"]("project", "group", "layer")), {"id": "layer"})
            self.assertEqual(fake.resources["sketchtoui://projects/{project_id}/groups/{group_id}/artboards/{artboard_id}/preview"]("project", "group", "artboard"), b"png")
            prompt = fake.prompts["analyze_design_page"]("sketchtoui://projects/project", "layout")
            self.assertIn("layout", prompt[0]["content"])
            response = asyncio.run(fake.routes["/health"](None))
            self.assertEqual(response.status_code, 200)
        self.assertTrue(fake.app.middleware)


if __name__ == "__main__":
    unittest.main()
