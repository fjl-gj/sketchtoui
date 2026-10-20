# SketchToUI 架构设计

> 版本：v1.0\
> 更新日期：2026-10-20\
> 需求基线：[产品需求文档](01_PRODUCT_REQUIREMENTS.md) · [数据库表结构](05_DATABASE_SCHEMA.md)

## 1. 架构目标

SketchToUI 的架构首先服务于设计上下文质量，而不是先服务于支付或团队功能。

默认单机运行使用 SQLite、进程内内存缓存和本地 `data/storage`，无需 Redis、MinIO。多实例部署可选择 Redis 共享会话与限流，文件使用共享持久卷或 MinIO；下文公网部署图展示外部依赖方案。内存缓存重启后失效，MCP Token 与项目索引仍在数据库中；Web、MCP 的本地文件目录必须一致。

1. **可信解析**：稳定提取 Sketch 的页面、画板、图层、文本、样式、资源和 Path 数据。
2. **可验证视觉**：用户可通过交互画布、原始预览、画板预览和图层属性判断解析是否正确。
3. **精准 MCP 上下文**：外部 AI 按项目、分组、画板、图层逐层读取，而不是取得无边界的大 JSON。
4. **严格数据隔离**：Web、资源和 MCP 请求只能访问所属用户的数据。
5. **可演进性**：后续增加版本、会员、支付或团队功能时，不推倒解析、画布和 MCP 核心。

## 2. 架构原则

| 原则 | 决策 |
| --- | --- |
| 单一事实来源 | Sketch 原文件和解压内容在本地目录或对象存储；SQLite / MySQL 保存业务索引；内存缓存 / Redis 只保存短期状态。 |
| 分层读取 | UI 与 MCP 都使用“项目 → 分组 → 画板 → 图层”的渐进读取方式。 |
| 视觉优先校验 | 原始 `previews/preview.png`、画板 PNG 与 Canvas 共同验证还原质量。 |
| 权限前置 | 每次对象读取前校验用户、项目、分组和资源归属；Bucket 默认私有。 |
| 前端交互独立 | 视口、选中、悬停与检查器解耦，普通 UI 更新不能重置画布。 |
| MCP 不承担生成 | MCP 提供设计上下文；Codex/Cursor 等外部 AI 负责模型调用和代码生成。 |
| 先功能后商业化 | 会员与支付只能建立在稳定解析、稳定画布和稳定 MCP 上。 |

## 3. 系统上下文图

```mermaid
flowchart LR
    User["设计师 / 开发者"]
    AI["Codex / Cursor 等外部 AI"]
    Web["sketchtoui.com\nReact Web 工作台"]
    API["Flask 业务 API"]
    MCP["mcp.sketchtoui.com\nRemote MCP"]
    DB[("SQLite / MySQL")]
    Cache[("内存 / Redis")]
    Storage[("本地目录 / MinIO\n私有文件")]
    Mail["SMTP 邮箱服务"]
    Pay["第三方支付\n后续接入"]

    User --> Web
    Web --> API
    AI -->|"Bearer MCP Token"| MCP
    API --> DB
    API --> Cache
    API --> Storage
    API --> Mail
    MCP --> DB
    MCP --> Cache
    MCP --> Storage
    API -. "创建订单 / 回调验签" .-> Pay
```

## 4. 公网部署边界

```mermaid
flowchart TB
    Internet["公网用户 / AI 客户端"]
    Proxy["Nginx / HTTPS 反向代理"]
    WebStatic["React 生产构建\ncanvas-react/dist"]
    Flask["Flask API\n127.0.0.1:8123"]
    McpServer["Uvicorn MCP\n127.0.0.1:8124"]
    MySQL[("MySQL\n内网")]
    Redis[("Redis\n内网")]
    ObjectStore[("MinIO / OSS\n私有 Bucket")]

    Internet -->|"https://sketchtoui.com"| Proxy
    Internet -->|"https://mcp.sketchtoui.com/mcp"| Proxy
    Proxy -->|"/"| WebStatic
    Proxy -->|"/api/*"| Flask
    Proxy -->|"mcp 子域名 /mcp"| McpServer
    Flask --> MySQL
    Flask --> Redis
    Flask --> ObjectStore
    McpServer --> MySQL
    McpServer --> Redis
    McpServer --> ObjectStore
```

公网只开放 HTTPS 反向代理。MySQL、Redis、对象存储管理端口、Flask 与 MCP 的真实监听端口均只允许内网或 `127.0.0.1` 访问。

## 5. 逻辑组件图

```mermaid
flowchart TB
    subgraph Frontend["React 工作台"]
        Auth["认证卡片"]
        Projects["项目管理"]
        Navigator["平台 / 页面 / 画板目录"]
        Canvas["CanvasStage\n平移、缩放、命中测试、选中框"]
        Inspector["图层属性检查器"]
        McpPanel["MCP Token 管理"]
    end

    subgraph Backend["Flask 业务 API"]
        AuthAPI["认证控制器"]
        ProjectAPI["项目 / 导入 / 资源控制器"]
        McpAPI["MCP Token 控制器"]
        ImportSvc["导入编排服务"]
        Parser["Sketch 解析核心"]
        CanvasBuild["Canvas 数据构建器"]
        AssetSvc["私有资源读取"]
        Entitlement["权益服务\n后续"]
    end

    subgraph RemoteMCP["Remote MCP"]
        TokenVerify["Bearer Token 验证"]
        RateLimit["内存 / Redis 限流"]
        DesignSvc["设计上下文服务"]
        PreviewSvc["画板预览服务"]
    end

    Auth --> AuthAPI
    Projects --> ProjectAPI
    Navigator --> ProjectAPI
    Canvas --> ProjectAPI
    Inspector --> ProjectAPI
    McpPanel --> McpAPI
    ProjectAPI --> ImportSvc
    ImportSvc --> Parser
    Parser --> CanvasBuild
    ProjectAPI --> AssetSvc
    TokenVerify --> DesignSvc
    RateLimit --> DesignSvc
    DesignSvc --> PreviewSvc
```

## 6. 数据职责与对象组织

| 存储 | 保存内容 | 生命周期 | 访问规则 |
| --- | --- | --- | --- |
| SQLite / MySQL | 用户、项目索引、MCP Token、后续版本/订阅/订单 | 长期 | 仅后端服务可访问。 |
| 内存缓存 / Redis | Session、验证码、重发冷却、导入进度、限流 | 短期 | 必须设置 TTL；不保存长期业务事实，内存模式按进程隔离。 |
| 本地目录 / MinIO | 原始 Sketch、解压数据、图片、Canvas JSON、预览图 | 长期 | 私有目录 / Bucket；先校验项目归属。 |
| 本地临时目录 | 上传文件、解压工作区、解析中间文件 | 短期 | 成功、失败或异常后均清理。 |

推荐对象存储前缀：

```text
users/{user-id}/projects/{project-id}/
  source/{original-file}.sketch
  sketch/...
  canvas/manifest.json
  canvas/{group-directory}/canvas.json
  previews/{artboard-id}.png
  versions/{version-id}/...
```

对象路径不能由前端自由拼接后直读；后端必须从当前用户和项目 ID 构造受控前缀。

## 7. 导入与解析数据流

```mermaid
sequenceDiagram
    participant Browser as React 浏览器
    participant API as Flask API
    participant Redis as 内存缓存 / Redis
    participant Task as Flask 后台任务池
    participant Store as 本地目录 / MinIO
    participant DB as MySQL

    Browser->>API: POST /api/projects (.sketch)
    API->>DB: 创建项目 / 导入记录
    API->>Store: 保存原始 Sketch
    API->>Redis: 创建导入任务状态
    API->>Task: 提交项目导入任务
    API-->>Browser: 202 + jobId
    loop 进度查询
        Browser->>API: GET /api/imports/{jobId}
        API->>Redis: 查询进度
        API-->>Browser: 上传/解压/解析/生成状态
    end
    Task->>Task: 复制为 ZIP 并受限解压
    Task->>Task: 解析 meta/document/user/pages/images
    Task->>Task: 构建 Canvas JSON 与 manifest
    Task->>Store: 保存 canvas 与资源索引
    Task->>DB: 更新项目状态、分组数、版本信息
    Task->>Redis: 标记任务完成
```

解析必须拆为六层：页面定位、目标页面读取、节点规范化、视觉框计算、资源关联、Canvas/manifest 构建。`meta.json → pagesAndArtboards` 用于定位 Sketch 页面；只读取目标 `pages/{page-id}.json`，不得混入无关页面或画板。

## 8. Web 工作台架构

```mermaid
flowchart LR
    State["工作区状态\n项目 / 分组 / 当前画板 / 选中图层"]
    Viewport["独立视口状态\nscale / translateX / translateY"]
    Tree["虚拟图层树"]
    Stage["CanvasStage"]
    Inspector["Inspector"]
    Hover["Hover Tooltip"]

    State --> Tree
    State --> Stage
    State --> Inspector
    Viewport --> Stage
    Stage -->|"onSelect"| State
    Tree -->|"onSelect"| State
    Stage -->|"onViewportChange"| Viewport
    Stage -->|"onHover"| Hover
```

关键约束：

- 视口状态不依赖目录展开、右侧抽屉、悬停提示等普通 UI 状态；它们不得触发缩放/平移重置。
- 切换画板时仅在明确选中时执行一次初始聚焦；旧异步请求必须被取消或忽略。
- 图层树只接收当前 Artboard 的节点，并使用虚拟列表。
- 右侧检查器只显示单个选中节点的自身数据，默认不递归完整子树。
- 渲染、命中测试、选中框与重叠检测共用统一 `visualFrame` 定义。

## 9. Remote MCP 架构

```mermaid
sequenceDiagram
    participant AI as Codex / Cursor
    participant MCP as Remote MCP
    participant Limit as 内存 / Redis 限流
    participant Token as Token 服务
    participant Design as 设计上下文服务
    participant DB as MySQL
    participant Store as 本地目录 / MinIO

    AI->>MCP: Authorization: Bearer skt_...
    MCP->>Limit: 全局 + Token 频率检查
    Limit-->>MCP: 允许 / 429
    MCP->>Token: 哈希校验 Token、启用状态
    Token->>DB: 查找 Token 与 user_id
    Token-->>MCP: 当前用户身份
    MCP->>Design: 请求项目 / 分组 / 画板 / 图层
    Design->>DB: 校验项目 user_id
    Design->>Store: 读取受控 Canvas / 资源对象
    Design-->>MCP: 精确结构、图片或预览
    MCP-->>AI: Tool / Resource 结果
```

MCP 采用渐进式读取：项目列表 → 页面分组 → 画板 → 有限深度上下文或单图层 → 预览 PNG / 图片资产 / 设计 Token / 组件摘要。预览和资产使用同一 Bearer Token 权限，不能依赖浏览器 Cookie。

## 10. 解析与视觉质量架构

| 层次 | 作用 | 典型字段 |
| --- | --- | --- |
| 原始事实 | 保留 Sketch 源信息，便于排错和二次解析。 | `sourceFrame`、points、文本 Run、原始 style。 |
| 规范化事实 | 供 Web、MCP、导出共同消费。 | `frame`、`visualFrame`、字体、颜色、资源引用。 |
| 视觉验证事实 | 判断最终显示是否接近设计稿。 | 原始 preview、生成 artboard preview、差异结果。 |

- 文本以 Run 为最小样式单位，综合 `sourceFrame`、段落、行高和垂直对齐计算位置，不能强制所有文本居中。
- Shape Path 保留点、曲线控制点、`curveMode`，再构建正确 SVG Path。
- Bitmap、Symbol 和无法可靠由 Path 重建的图标优先使用 Sketch 引用的资源。
- Canvas 渲染器和画板预览服务应复用颜色、边框、圆角、变换和视觉框计算逻辑。
- 原始预览图是回归参照，不是替代解析数据的最终实现。

## 11. 后续商业化扩展位

```mermaid
flowchart LR
    User["用户"] --> API["Flask API"]
    API --> Entitlement["权益服务"]
    Entitlement --> Subscription[("订阅 / 套餐")]
    API --> Order["订单服务"]
    Order --> Payment["第三方支付 Adapter"]
    Payment --> Webhook["支付回调验签"]
    Webhook --> Subscription
    Entitlement --> ProjectLimit["项目 / 存储限制"]
    Entitlement --> McpLimit["高级 MCP 能力"]
```

会员和支付不进入当前核心数据流。后续仅保留免费版与个人会员（`¥9/月`、`¥96/年`），不销售平台 AI Token，也不把 AI 自动生成代码作为平台可控承诺。

## 12. 架构决策记录

| 编号 | 决策 | 原因 |
| --- | --- | --- |
| ADR-001 | Web 与 API 同一主域名 | 当前前端 API 使用相对路径，降低跨域和 Cookie 复杂度。 |
| ADR-002 | MCP 使用独立子域名 | 便于 Remote MCP 配置、限流、日志和安全边界。 |
| ADR-003 | Bucket 默认私有 | Sketch 资源可能含敏感业务信息。 |
| ADR-004 | 内存缓存 / Redis 保存短期状态 | Session、验证码、任务状态和限流均带 TTL；默认内存，多进程共享时选择 Redis。 |
| ADR-005 | MySQL 保存业务事实 | 用户、项目、Token、版本、订阅和订单必须可迁移和备份。 |
| ADR-006 | 导入采用受限后台任务池 | 当前单机阶段以最少进程实现异步解析；所选缓存保存进度，数据库保存恢复记录，压力出现后再拆分独立 Worker。 |
| ADR-007 | MCP 采用手工 Token | 当前优先保证可用、隔离和启停管理，不实现 OAuth。 |
| ADR-008 | 不销售 AI Token | 平台专注设计上下文，外部 AI 负责模型调用。 |
