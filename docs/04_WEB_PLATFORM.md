# Sketch 本地 Web 平台

该平台支持在浏览器中注册账户、验证邮箱、导入 `.sketch` 文件、保存原文件和解压内容、按 `meta.json` 解析画布分组，并在 React 画布中查看图层、属性和图片资源。

## 配置与启动

首次安装后端依赖：

```powershell
# 在克隆后的仓库根目录执行
python -m pip install -r requirements.txt
```

开发与回归测试环境可安装额外工具：

```powershell
python -m pip install -r requirements-dev.txt
```

首次使用前，复制根目录的 `.env.example` 为 `.env`。默认使用 SQLite、`CACHE_BACKEND=memory` 和 `STORAGE_BACKEND=local`，无需 Redis 或 MinIO。邮箱默认 `EMAIL_DELIVERY=console`，从后端输出读取 6 位注册验证码；正式环境改为 `smtp` 并配置 `SMTP_*`。后续切换 MySQL 时只需将 `DATABASE_DSN` 改为 MySQL 连接串。验证码、重发冷却、登录 Session 和实时导入进度保存在所选缓存中，具有自动过期时间。

可选配置：`CACHE_BACKEND=redis` 配合 `REDIS_URL`；`STORAGE_BACKEND=minio` 配合 `MINIO_ENDPOINT`、`MINIO_ACCESS_KEY`、`MINIO_SECRET_KEY` 和 `MINIO_BUCKET`。已有配置未设置选择项时，按是否存在 `REDIS_URL` / `MINIO_ENDPOINT` 继续选用外部后端；显式选择 `memory` / `local` 可忽略旧连接配置。连接失败不会自动降级，以免会话或文件分散在不同后端。

开发模式使用三个终端：

```powershell
# 终端 1：后端
# 在仓库根目录执行（已激活 Python 虚拟环境）
python .\backend\main.py
```

```powershell
# 终端 2：前端
# 在仓库根目录执行
npm --prefix canvas-react run dev -- --host 127.0.0.1
```

```powershell
# 终端 3：Remote MCP
# 在仓库根目录执行（已激活 Python 虚拟环境）
python .\backend\mcp_main.py
```

开发页面地址为 `http://127.0.0.1:8122`；Flask API 为 `http://127.0.0.1:8123`，Remote MCP 为 `http://127.0.0.1:8124/mcp`。也可以直接双击根目录的 `start-services.cmd` 启动这三个服务，使用 `stop-services.cmd` 停止由该脚本启动的服务。Sketch 解析由 Flask 进程中的受限后台任务池执行，内存缓存或 Redis 保存实时进度，数据库保存可恢复的任务记录。

后端服务代码位于 `backend/`，测试 Sketch 样本位于 `fixtures/sketch/`；`data/tmp/` 只在导入与解析期间保存临时文件。

## 回归验证

运行后端解析与预览回归测试：

```powershell
# 在仓库根目录执行
.\.venv\Scripts\python.exe -m unittest discover -s backend\tests -v
```

生成后端覆盖率报告：

```powershell
# 在仓库根目录执行
.\.venv\Scripts\python.exe -m coverage run --source=backend --omit="backend/tests/*" -m unittest discover -s backend\tests -v
.\.venv\Scripts\python.exe -m coverage report -m
```

构建前端并校验 TypeScript：

```powershell
# 在仓库根目录执行
npm --prefix canvas-react run build
```

构建后的单服务运行方式：

```powershell
# 在仓库根目录执行（已激活 Python 虚拟环境）
npm --prefix canvas-react run serve
```

然后打开 `http://127.0.0.1:8123`，点击右上角“导入 Sketch”选择文件。

## 本地存储

用户、项目、导入记录和 MCP Token 保存在 SQLite（可通过 `DATABASE_DSN` 切换为 MySQL）；短期状态默认保存在内存，也可使用 Redis。原始 Sketch、解压内容、图片与 Canvas JSON 默认保存在 `data/storage/users/...`，可通过 `LOCAL_STORAGE_DIR` 改为其他相对仓库根目录的路径或绝对目录，也可选择 MinIO。Web 和 MCP 必须指向同一文件目录，目录需要持久化并与数据库一起备份；文件仍经用户/项目权限校验后读取，不应公开为静态目录。`data/tmp/` 仅作为导入期间的临时工作目录，任务结束自动清理。

内存缓存适用于单个 Web 进程、多线程运行；重启后 Session 和验证码失效，MCP 限流按进程计数。多 Web Worker / 多实例应使用 Redis，共享文件应使用持久卷或 MinIO。切换存储后旧文件不会自动迁移；需要保持原有对象相对路径迁移文件，或保留原后端。
