# SketchToUI

[![CI](https://github.com/fjl-gj/sketchtoui/actions/workflows/ci.yml/badge.svg)](https://github.com/fjl-gj/sketchtoui/actions/workflows/ci.yml)

**Sketch designs → browser canvas → AI design context.**

Import `.sketch` files into a React workspace, inspect artboards and layers, and share structured design context, assets, and previews with AI clients through an authenticated, read-only Remote MCP server.

将 Sketch 设计文件导入浏览器工作台，查看设计页面、图层、文字和图片，并通过带认证的 Remote MCP 将设计上下文提供给 AI 客户端。

[快速开始](#快速开始windows-powershell) · [一键启停](#一键启停) · [MCP 接入](REMOTE_MCP.md) · [架构文档](docs/02_ARCHITECTURE.md) · [贡献指南](CONTRIBUTING.md)

项目当前提供设计解析、浏览和上下文读取能力；生产代码生成由连接的 AI 客户端根据设计上下文完成。

## 功能

- 邮箱注册、验证与登录，按用户管理项目。
- 导入 `.sketch` 文件，在后台解析页面分组、画板与图层。
- React Canvas 画布支持缩放、平移、图层选择和属性查看。
- 将原始文件、图片和解析结果保存至 MinIO。
- 创建、禁用和撤销个人 MCP Token，通过只读工具和 `sketchtoui://` Resource 读取设计数据。
- 获取画板预览、设计规范、重复组件候选，以及文本布局和图层重叠分析。

## 工作方式

```mermaid
flowchart LR
    Design["Sketch 文件"] --> Web["浏览器工作台"]
    Web --> API["Flask API 与后台解析"]
    API --> DB["SQLite / MySQL：账号与项目索引"]
    API --> Cache["Redis：会话与任务进度"]
    API --> Storage["MinIO：设计、图层数据与图片"]
    Client["AI 客户端 + 个人 Token"] --> MCP["只读 Remote MCP"]
    MCP --> DB
    MCP --> Cache
    MCP --> Storage
```

## 技术栈与依赖

| 部分 | 实现 |
| --- | --- |
| 前端 | React、TypeScript、MUI、Vite |
| Web API | Python、Flask |
| Remote MCP | MCP Python SDK、Streamable HTTP、Uvicorn |
| 数据库 | 本地 SQLite / MySQL，Alembic 迁移 |
| 缓存与会话 | Redis |
| 文件存储 | MinIO |

准备 Python 3.12、Node.js 22.12 或更新版本，以及可访问的 Redis 和 MinIO。Redis 和 MinIO 是启动必需的依赖；本仓库不包含它们的数据和访问凭据。

## 快速开始（Windows PowerShell）

先克隆项目，再在仓库根目录安装依赖：

```powershell
git clone https://github.com/fjl-gj/sketchtoui.git
cd sketchtoui
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
npm --prefix canvas-react ci
Copy-Item .env.example .env
```

编辑 `.env`，按自己的环境填写：

| 配置 | 说明 |
| --- | --- |
| `DATABASE_DSN` | 本地可保留 `sqlite:///data/workspace/sketch.db`；MySQL 使用 `mysql://user:password@host:3306/sketchtoui` |
| `REDIS_URL` | 可访问的 Redis 地址 |
| `MINIO_ENDPOINT` | MinIO 的 `host:port`，不包含协议前缀 |
| `MINIO_ACCESS_KEY` / `MINIO_SECRET_KEY` | 你自己的 MinIO 访问凭据 |
| `MINIO_BUCKET` | 保存设计文件的存储桶；应用启动时会检查并在不存在时创建 |
| `EMAIL_DELIVERY` | 本地调试改为 `console`，从后端输出读取注册验证码；正式环境使用 `smtp` 并配置 `SMTP_*` |

初始化一个新数据库：

```powershell
New-Item -ItemType Directory -Path data/workspace -Force | Out-Null
.\.venv\Scripts\python.exe backend/manage.py db upgrade
```

已有数据库的迁移方式见 [Remote MCP 与数据库迁移说明](REMOTE_MCP.md)。应用不会自动执行数据库迁移。

### 一键启停

完成依赖安装、环境配置和数据库迁移后，运行：

```powershell
.\start-services.cmd
```

| 服务 | 本地地址 |
| --- | --- |
| 前端开发页面 | <http://127.0.0.1:8122> |
| Web API 健康检查 | <http://127.0.0.1:8123/api/health> |
| Remote MCP | <http://127.0.0.1:8124/mcp> |
| MCP 健康检查 | <http://127.0.0.1:8124/health> |

查看状态与停止服务：

```powershell
.\.venv\Scripts\python.exe scripts/services.py status
.\stop-services.cmd
```

启停脚本只管理本项目的三个应用进程，适用于 Windows；Redis 和 MinIO 需要单独启动。日志位于 `data/tmp/services/`，包括 `backend.stdout.log`、`backend.stderr.log` 和 MCP 日志。使用 `console` 邮件模式时，注册验证码写入后端输出日志。

首次使用时在页面注册自己的账号，导入自己的 `.sketch` 文件。仓库不提供默认账号、密码或私人设计样本。

### 分别启动 / macOS、Linux

在 macOS 或 Linux 上创建并激活虚拟环境后使用 `python`，Windows 可使用 `.venv\Scripts\python.exe`。安装、配置和迁移完成后，分别在三个终端运行：

```sh
# 前端
npm --prefix canvas-react run dev -- --host 127.0.0.1

# Web API
python backend/main.py

# Remote MCP
python backend/mcp_main.py
```

### 构建后由后端提供页面

```sh
npm --prefix canvas-react run build
python backend/main.py
```

然后访问 <http://127.0.0.1:8123>。Remote MCP 仍需单独启动。

## 连接 MCP 客户端

登录页面后点击 `MCP` 创建个人 Token，保存至客户端环境变量 `SKETCHTOUI_MCP_TOKEN`，在支持 Remote MCP 的客户端配置服务地址。页面右上角可以复制当前设计页面的 `sketchtoui://...` 链接。

完整的工具列表、Resource 格式和客户端配置示例见 [REMOTE_MCP.md](REMOTE_MCP.md)。

## 验证

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s backend/tests -v
npm --prefix canvas-react run build
```

测试使用合成输入、临时 SQLite 数据库和模拟依赖，无需私人 Sketch 样本。GitHub Actions 会运行后端单元测试和前端构建。

## 目录

```text
backend/          Flask API、MCP、Sketch 解析与单元测试
canvas-react/     React 工作台及其依赖锁文件
migrations/       Alembic 数据库迁移
scripts/          Windows 一键启停工具
docs/             产品、架构、技术方案和数据库文档
fixtures/         本地样本的放置说明
.env.example      不含真实凭据的环境配置模板
start-services.cmd
stop-services.cmd
```

运行数据、私人设计输入、生成画布、依赖目录、构建输出、本地助手配置和部署归档由 `.gitignore` 排除；现有本地文件保留在原处。

## 部署与故障检查

部署前安装依赖、构建前端、配置 `.env` 并执行数据库迁移。Web 与 MCP 需要独立的进程管理；正式部署使用 WSGI 服务提供 Flask 应用，并通过 HTTPS 反向代理暴露 Web 和 MCP。

如果进程不断退出且端口没有监听，先检查数据库、Redis 与 MinIO 的连接和权限。应用会在启动时连接这些依赖；MinIO 的 `/minio/health/live` 可以检查存储服务是否在线。Web `/api/health` 返回应用配置摘要，不会逐次探测所有外部依赖；完整验收还需要测试登录、导入及图片读取。

## 更多文档

- [目录职责](docs/README.md)
- [本地运行与存储](docs/04_WEB_PLATFORM.md)
- [架构](docs/02_ARCHITECTURE.md)
- [技术方案](docs/03_TECHNICAL_SOLUTION.md)
- [数据库结构](docs/05_DATABASE_SCHEMA.md)
- [贡献与验证](CONTRIBUTING.md)
