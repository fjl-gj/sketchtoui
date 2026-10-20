# 项目目录说明

```text
sketchtoui/
├─ backend/       Python 后端、Sketch 解析器与命令行工具
├─ canvas-react/  React + TypeScript 前端工作台
├─ data/          开发 SQLite 与导入期间临时解析目录
├─ docs/          项目说明文档
├─ fixtures/      本地样本说明（私人 Sketch 与生成数据不提交）
├─ .env           本地配置（不提交）
└─ requirements.txt
```

## `backend/`

- `main.py`：Flask 服务入口，内置受限并发的 Sketch 后台解析任务。
- `app/`：Flask 应用工厂、配置、通用组件、控制器与服务层。
- `app/common/database.py`、`app/common/extensions.py`：MySQL、Redis 与 MinIO 客户端初始化。
- `sketch_to_page_json.py`、`sketch_to_canvas_site.py`：Sketch 解析与画布数据生成。
- `sketch_to_json.py`、`sketch_to_struct.py`、`sketch_extract_artboard.py`：开发分析工具。

## `canvas-react/`

浏览器端 React 工作台，负责登录入口、项目管理、导入进度、图层虚拟列表与 Canvas 画布交互。

## `data/`

运行时目录，默认包括：

- `workspace/sketch.db`：开发阶段的 SQLite 用户与项目索引；切换到 MySQL 后可删除。
- `tmp/<导入任务 ID>/`：导入期间临时解压和解析目录，上传完成后自动清理。

该目录已在 `.gitignore` 中忽略。

## `fixtures/`

仅放开发与测试使用的输入样本。`fixtures/sketch/` 下的私人样本不提交到 Git；现有本地样本可继续保留在 `fixtures/sketch/test_001/`，不参与线上运行时存储。正式文件保存到 MinIO，后端单元测试使用自行生成的最小输入。

## `docs/`

仅放说明文档：

- `04_WEB_PLATFORM.md`：启动方式、环境配置与存储说明。
- `README.md`：目录职责说明。
- `01_PRODUCT_REQUIREMENTS.md`：产品需求、功能边界、优先级、验收标准与解析回归案例。
- `02_ARCHITECTURE.md`：系统架构、Mermaid 图、组件职责、数据流与架构决策。
- `03_TECHNICAL_SOLUTION.md`：后端、解析、画布、MCP、数据模型、测试与分阶段技术方案。
- `05_DATABASE_SCHEMA.md`：当前与目标 MySQL 表结构、字段、索引、关系、Redis Key、删除策略与 Alembic 迁移规划。
