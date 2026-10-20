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

首次使用前，复制根目录的 `.env.example` 为 `.env`，填写 `DATABASE_DSN`、`REDIS_URL`、`MINIO_*` 与 `SMTP_*` 配置。当前开发配置使用 SQLite 保存用户与项目索引；后续切换 MySQL 时只需将 `DATABASE_DSN` 改为 MySQL 连接串。注册后系统发送 6 位邮箱验证码；验证码、重发冷却、登录 Session 和导入进度仅保存在 Redis，具有自动过期时间。

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

开发页面地址为 `http://127.0.0.1:8122`；Flask API 为 `http://127.0.0.1:8123`，Remote MCP 为 `http://127.0.0.1:8124/mcp`。也可以直接双击根目录的 `start-services.cmd` 启动这三个服务，使用 `stop-services.cmd` 停止由该脚本启动的服务。Sketch 解析由 Flask 进程中的受限后台任务池执行，Redis 只保存实时进度。

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

用户和项目索引当前保存在 SQLite（可通过 `DATABASE_DSN` 切换为 MySQL）；登录 Session、邮箱验证码、重发冷却和导入进度保存在 Redis；原始 Sketch、解压内容、图片与 Canvas JSON 保存在 MinIO。`data/tmp/` 仅作为导入期间的临时工作目录，任务结束自动清理。
