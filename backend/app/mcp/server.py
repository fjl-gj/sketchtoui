from __future__ import annotations

import json
import mimetypes
from typing import Any
from urllib.parse import unquote

from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.auth.provider import AccessToken
from mcp.server.auth.settings import AuthSettings
from mcp.server.fastmcp import FastMCP, Image
from starlette.requests import Request
from starlette.responses import JSONResponse

from ..config.settings import settings
from ..services.mcp_design_service import McpDesignService
from ..services.mcp_token_service import McpTokenService
from ..services.artboard_preview_service import ArtboardPreviewService
from ..services.project_import_service import ProjectImportService
from .rate_limit import McpRateLimitMiddleware


class SketchToUiTokenVerifier:
    def __init__(self, service: McpTokenService) -> None:
        self.service = service

    async def verify_token(self, token: str) -> AccessToken | None:
        record = self.service.authenticate(token)
        if not record:
            return None
        return AccessToken(
            token=token,
            client_id=f"sketchtoui:{record['id']}",
            scopes=record["scopes"],
            subject=record["user_id"],
            claims={"username": record["username"], "tokenName": record["name"]},
        )


def current_user_id() -> str:
    access_token = get_access_token()
    if not access_token or not access_token.subject:
        raise PermissionError("缺少有效的 SketchToUI MCP Token")
    return access_token.subject


def create_mcp_app() -> Any:
    token_service = McpTokenService()
    design_service = McpDesignService()
    preview_service = ArtboardPreviewService()
    project_service = ProjectImportService()
    server = FastMCP(
        "SketchToUI Remote MCP",
        instructions="通过项目、页面分组和设计页面链接读取 SketchToUI 的只读设计上下文。所有工具仅返回当前 MCP Token 所属用户的数据。",
        host=settings.mcp_host,
        port=settings.mcp_port,
        streamable_http_path="/mcp",
        json_response=True,
        stateless_http=True,
        token_verifier=SketchToUiTokenVerifier(token_service),
        auth=AuthSettings(
            issuer_url=settings.mcp_issuer_url,
            resource_server_url=settings.mcp_public_url,
            required_scopes=["design:read"],
        ),
    )

    @server.tool()
    def list_projects() -> dict[str, Any]:
        """列出当前 MCP Token 可访问的 SketchToUI 项目。"""
        return {"projects": design_service.list_projects(current_user_id())}

    @server.tool()
    def list_page_groups(project_id: str) -> dict[str, Any]:
        """列出项目的电脑端/H5 页面分组。"""
        return design_service.list_page_groups(current_user_id(), project_id)

    @server.tool()
    def list_artboards(project_id: str, group_id: str) -> dict[str, Any]:
        """列出一个页面分组内的设计页面（画板）。"""
        return design_service.list_artboards(current_user_id(), project_id, group_id)

    @server.tool()
    def get_design_context(resource: str, depth: int = 2, max_nodes: int = 200) -> dict[str, Any]:
        """读取一个 sketchtoui:// 设计页面链接的结构、样式与有限层级子图层。"""
        return design_service.get_design_context(current_user_id(), resource, depth, max_nodes)

    @server.tool()
    def find_layers(project_id: str, query: str, group_id: str | None = None, artboard_id: str | None = None, limit: int = 30) -> dict[str, Any]:
        """按图层名称、图层类型或文本内容搜索图层。"""
        return design_service.find_layers(current_user_id(), project_id, query, group_id, artboard_id, limit)

    @server.tool()
    def get_layer(project_id: str, group_id: str, layer_id: str) -> dict[str, Any]:
        """读取一个图层自身的数据，不包含其完整子树。"""
        return design_service.get_layer(current_user_id(), project_id, group_id, layer_id)

    @server.tool()
    def inspect_text_layout(project_id: str, group_id: str, layer_id: str) -> dict[str, Any]:
        """检查文本图层的字体、字重、行高、文本框和对齐数据。"""
        return design_service.inspect_text_layout(current_user_id(), project_id, group_id, layer_id)

    @server.tool()
    def check_overlap(project_id: str, group_id: str, first_layer_id: str, second_layer_id: str) -> dict[str, Any]:
        """检测同一分组中的两个图层是否在视觉框上重叠。"""
        return design_service.check_overlap(current_user_id(), project_id, group_id, first_layer_id, second_layer_id)

    @server.tool()
    def get_design_tokens(project_id: str, group_id: str | None = None) -> dict[str, Any]:
        """汇总颜色、排版、圆角和阴影，供前端还原设计系统。"""
        return design_service.get_design_tokens(current_user_id(), project_id, group_id)

    @server.tool()
    def list_reusable_components(project_id: str, group_id: str | None = None) -> dict[str, Any]:
        """列出重复出现的分组、形状组和 Symbol 组件候选。"""
        return design_service.list_reusable_components(current_user_id(), project_id, group_id)

    @server.tool()
    def get_artboard_preview(project_id: str, group_id: str, artboard_id: str) -> Image:
        """生成设计页面的 PNG 预览，便于视觉比对与 UI 还原。"""
        return Image(data=preview_service.render(current_user_id(), project_id, group_id, artboard_id), format="png")

    @server.tool()
    def get_design_asset(project_id: str, asset_path: str) -> Image:
        """读取 Sketch 中引用的图片或图标资源。asset_path 使用图层 image.reference 的值。"""
        payload, content_type = project_service.read_object(current_user_id(), project_id, f"sketch/{asset_path}")
        if not content_type.startswith("image/"):
            raise ValueError("目标资源不是图片")
        image_format = mimetypes.guess_extension(content_type) or ".png"
        return Image(data=payload, format=image_format.removeprefix("."))

    @server.resource(
        "sketchtoui://projects",
        name="design_projects",
        title="SketchToUI 项目目录",
        description="列出当前 MCP Token 可访问的 SketchToUI 项目。",
        mime_type="application/json",
    )
    def read_projects_resource() -> str:
        """读取当前用户的项目目录。"""
        return json.dumps({"projects": design_service.list_projects(current_user_id())}, ensure_ascii=False, indent=2)

    @server.resource(
        "sketchtoui://projects/{project_id}",
        name="design_project",
        title="SketchToUI 项目",
        description="读取一个项目及其电脑端、H5 页面分组。",
        mime_type="application/json",
    )
    def read_project_resource(project_id: str) -> str:
        """读取项目资源。"""
        return json.dumps(design_service.list_page_groups(current_user_id(), unquote(project_id)), ensure_ascii=False, indent=2)

    @server.resource(
        "sketchtoui://projects/{project_id}/groups/{group_id}",
        name="design_page_group",
        title="SketchToUI 页面分组",
        description="读取一个电脑端或 H5 页面分组及其设计页面目录。",
        mime_type="application/json",
    )
    def read_page_group_resource(project_id: str, group_id: str) -> str:
        """读取页面分组资源。"""
        return json.dumps(
            design_service.list_artboards(current_user_id(), unquote(project_id), unquote(group_id)),
            ensure_ascii=False,
            indent=2,
        )

    @server.resource(
        "sketchtoui://projects/{project_id}/groups/{group_id}/artboards/{artboard_id}",
        name="design_artboard",
        title="SketchToUI 设计页面",
        description="读取一个 SketchToUI 设计页面的画板、图层结构、样式和统计数据。",
        mime_type="application/json",
    )
    def read_artboard_resource(project_id: str, group_id: str, artboard_id: str) -> str:
        """读取一个设计页面资源。"""
        context = design_service.get_artboard_context(
            current_user_id(),
            unquote(project_id),
            unquote(group_id),
            unquote(artboard_id),
            depth=3,
            max_nodes=400,
        )
        return json.dumps(context, ensure_ascii=False, indent=2)

    @server.resource(
        "sketchtoui://projects/{project_id}/groups/{group_id}/layers/{layer_id}",
        name="design_layer",
        title="SketchToUI 单图层",
        description="读取一个 SketchToUI 图层本身的数据，不递归包含它的子图层。",
        mime_type="application/json",
    )
    def read_layer_resource(project_id: str, group_id: str, layer_id: str) -> str:
        """读取一个单图层资源。"""
        layer = design_service.get_layer(
            current_user_id(),
            unquote(project_id),
            unquote(group_id),
            unquote(layer_id),
        )
        return json.dumps(layer, ensure_ascii=False, indent=2)

    @server.resource(
        "sketchtoui://projects/{project_id}/groups/{group_id}/artboards/{artboard_id}/preview",
        name="design_artboard_preview",
        title="SketchToUI 设计页面 PNG 预览",
        description="读取设计页面的 PNG 预览，用于视觉比对与界面还原。",
        mime_type="image/png",
    )
    def read_artboard_preview_resource(project_id: str, group_id: str, artboard_id: str) -> bytes:
        """读取一个设计页面 PNG 预览资源。"""
        return preview_service.render(current_user_id(), unquote(project_id), unquote(group_id), unquote(artboard_id))

    @server.prompt(
        name="analyze_design_page",
        title="分析 SketchToUI 设计页面",
        description="根据设计页面资源生成页面结构、视觉规范与潜在布局问题分析。",
    )
    def analyze_design_page(resource: str, focus: str = "整体页面结构与可实现性") -> list[dict[str, Any]]:
        """构造一个使用指定设计页面资源的分析提示词。"""
        context = design_service.get_design_context(current_user_id(), resource, depth=3, max_nodes=400)
        page_data = json.dumps(context, ensure_ascii=False, indent=2)
        return [
            {
                "role": "user",
                "content": (
                    "请作为资深 UI 工程师分析以下 SketchToUI 设计页面数据。\n"
                    f"分析重点：{focus}\n\n"
                    "请输出：\n"
                    "1. 页面与图层层级概览；\n"
                    "2. 可复用组件、间距、色彩、字体和响应式实现建议；\n"
                    "3. 明确列出可能的重叠、裁切、文本框或定位风险；\n"
                    "4. 给出前端实现时应优先处理的事项。\n\n"
                    f"资源：{resource}\n\n"
                    f"页面数据：\n{page_data}"
                ),
            }
        ]

    @server.custom_route("/health", methods=["GET"], name="health")
    async def health_check(_request: Request) -> JSONResponse:
        """供反向代理、容器平台和后台状态检查使用。"""
        return JSONResponse(
            {
                "status": "ok",
                "service": "sketchtoui-remote-mcp",
                "mcpPath": "/mcp",
            }
        )

    app = server.streamable_http_app()
    app.add_middleware(
        McpRateLimitMiddleware,
        path="/mcp",
        per_token_limit=settings.mcp_rate_limit_per_minute,
        global_limit=settings.mcp_global_rate_limit_per_minute,
    )
    return app
