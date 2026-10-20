# SketchToUI Remote MCP

SketchToUI 提供一个独立的、认证后的 Streamable HTTP MCP 服务。它只读访问当前 MCP Token 所属用户的项目、页面分组、设计页面和图层数据。

## 1. 安装依赖

```powershell
# 在克隆后的仓库根目录执行
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## 数据库迁移

数据库结构由 Alembic 管理，迁移文件位于 `migrations/versions/`，应与应用代码一同提交到 Git。

新环境首次部署：

```powershell
python .\backend\manage.py db upgrade
```

已有的旧数据库已经具备当前全部表和字段时，不要重复执行初始建表迁移；首次接入 Alembic 使用：

```powershell
python .\backend\manage.py db stamp head
```

查看当前版本：

```powershell
python .\backend\manage.py db current
```

以后每次变更表、字段、索引时创建一个新的迁移文件：

```powershell
python .\backend\manage.py db revision -m "describe schema change"
```

## 2. 配置服务地址

开发环境可使用 `.env` 中的默认值：

```dotenv
MCP_HOST=127.0.0.1
MCP_PORT=8124
MCP_PUBLIC_URL=http://127.0.0.1:8124/mcp
MCP_ISSUER_URL=http://127.0.0.1:8123
```

生产环境必须将 `MCP_PUBLIC_URL` 设置为 HTTPS 公网地址，例如 `https://mcp.example.com/mcp`。

## 3. 启动服务

分别打开三个 PowerShell：

```powershell
# 在仓库根目录执行
npm --prefix canvas-react run dev
```

```powershell
# 在仓库根目录执行（已激活 Python 虚拟环境）
python .\backend\main.py
```

```powershell
# 在仓库根目录执行（已激活 Python 虚拟环境）
python .\backend\mcp_main.py
```

前端开发服务默认使用 `8122`，Web API 默认使用 `8123`，Remote MCP 默认使用 `8124/mcp`。

## 4. 创建个人 MCP Token

登录 SketchToUI 后，点击顶部的 `MCP`，创建一个 Token。完整 Token 只显示一次；请立刻复制并妥善保存。

Token 可在同一窗口中随时禁用或重新启用。禁用后，该 Token 立即无法读取任何项目数据；重新启用后可继续使用原有 Codex 配置。

## 5. 配置 Codex

在 Windows 用户环境变量中保存 Token：

```powershell
[Environment]::SetEnvironmentVariable("SKETCHTOUI_MCP_TOKEN", "skt_替换为你的Token", "User")
```

在当前用户的 Codex 配置文件（Windows 默认 `%USERPROFILE%\.codex\config.toml`）中添加配置，再完全退出并重新打开客户端：

```toml
[mcp_servers.sketchtoui]
enabled = true
url = "http://127.0.0.1:8124/mcp"
bearer_token_env_var = "SKETCHTOUI_MCP_TOKEN"
```

生产环境请将 `url` 替换为你的 HTTPS `MCP_PUBLIC_URL`。

## 6. 使用设计页面链接

在画布右上角点击 `复制 {页面名} MCP 链接`，然后将复制的 `sketchtoui://...` 链接粘贴到 Codex 提示词中，例如：

```text
分析这个设计页面的布局、文本样式与可能重叠的图层：
sketchtoui://projects/.../groups/.../artboards/...
```

## 可用工具

- `list_projects`
- `list_page_groups`
- `list_artboards`
- `get_design_context`
- `find_layers`
- `get_layer`
- `inspect_text_layout`
- `check_overlap`
- `get_design_tokens`：汇总颜色、文字、圆角、阴影等设计规范。
- `list_reusable_components`：查找重复分组、形状组和 Symbol 组件候选。
- `get_artboard_preview`：返回设计页面的 PNG 预览图片。
- `get_design_asset`：返回图层 `image.reference` 指向的原始图片或图标。

当前工具全部只读。撤销 Token 后，已经配置它的 Codex 会立即失去访问权限。

## Resources、Prompt 与健康检查

Remote MCP 也提供标准 MCP Resource，因此客户端可以直接读取数据，而不只通过 Tool 调用：

- 项目目录：`sketchtoui://projects`
- 单个项目：`sketchtoui://projects/{projectId}`
- 页面分组：`sketchtoui://projects/{projectId}/groups/{groupId}`
- 设计页面：`sketchtoui://projects/{projectId}/groups/{groupId}/artboards/{artboardId}`
- 设计页面预览：`sketchtoui://projects/{projectId}/groups/{groupId}/artboards/{artboardId}/preview`
- 单图层：`sketchtoui://projects/{projectId}/groups/{groupId}/layers/{layerId}`

其中 `groupId` 包含 `:` 时需要 URL 编码，例如 `desktop` 分组可形如
`748D2293-E71E-4046-BCB8-DAFFC5467DAC%3Adesktop`。图层 Resource 仅返回目标图层本身，不会递归展开子图层。

还提供 `analyze_design_page` Prompt：传入设计页面 Resource 后，可让支持 MCP Prompt 的客户端生成页面层级、视觉规范、组件拆分和布局风险分析。

无鉴权健康检查地址：

```text
http://127.0.0.1:8124/health
```

## 限流

MCP 服务使用所选缓存后端在入口进行固定窗口限流，防止大量并发请求占满服务。默认使用进程内内存，无需 Redis；设置 `CACHE_BACKEND=redis` 和 `REDIS_URL` 后可在多个进程间共享计数。内存模式的“全局”仅指当前 MCP 进程，重启后计数清空。默认每个 Token 每分钟最多 `600` 次请求，所有 MCP 请求合计每分钟最多 `6000` 次；正常浏览项目、读取图层和图片不会受到影响。

MCP 与 Web 读取同一个数据库和文件后端。默认 `STORAGE_BACKEND=local`、`LOCAL_STORAGE_DIR=data/storage`；两者必须访问同一持久目录。Token 验证从数据库读取，因此 Web 的内存 Session 无需共享给 MCP。多实例可选择共享持久卷或 MinIO。

可在 `.env` 调整：

```dotenv
MCP_RATE_LIMIT_PER_MINUTE=600
MCP_GLOBAL_RATE_LIMIT_PER_MINUTE=6000
MCP_PREVIEW_MAX_DIMENSION=1600
MCP_PREVIEW_FONT_PATH=C:/Windows/Fonts/msyh.ttc
```

将任一限流值设为 `0` 可关闭相应限制。预览图最长边默认不超过 `1600` 像素；若服务器未自动找到中文字体，请设置 `MCP_PREVIEW_FONT_PATH`。
