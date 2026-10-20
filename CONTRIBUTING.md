# 开发与贡献

先按 [README](README.md) 安装 Python 和前端依赖，复制 `.env.example` 并配置自己的开发环境。

## 修改范围

- Web 路由位于 `backend/app/controllers/`，业务逻辑位于 `backend/app/services/`。
- Sketch 解析工具位于 `backend/`，画布和界面位于 `canvas-react/src/`。
- 修改表、字段或索引时，在 `migrations/versions/` 增加新的 Alembic 迁移，保留既有迁移。
- 将功能变更和无关重构分开提交，并说明用户可观察到的行为变化。

## 检查

在仓库根目录运行：

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s backend/tests -v
npm --prefix canvas-react run build
git diff --check
```

macOS / Linux 在激活虚拟环境后将 Python 命令替换为 `python`。

后端回归用例位于 `backend/tests/`。新增解析场景时优先构造最小 Sketch JSON 或临时压缩包；测试不应依赖私人设计、线上服务、个人文件路径或真实账号。当前未配置独立的前端 lint/test 命令，前端构建会执行 TypeScript 检查。

## 提交前

确认暂存区不包含 `.env`、数据库、日志、Token、访问密钥、私人 Sketch、生成画布、依赖或构建产物。配置项使用 `.env.example` 中的占位值；运行数据与设计样本留在本地。

提交说明包含问题、改动和实际验证结果。Git 提交、推送、服务器部署和真实环境验收是独立步骤。
