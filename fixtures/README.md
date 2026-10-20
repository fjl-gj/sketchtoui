# 本地设计样本

本目录可在本机放置用于手动验证的 Sketch 文件，但不随源码发布私人设计和生成数据。

`fixtures/sketch/`、所有 `.sketch` 文件，以及 `canvas-react/public/canvas/` 和 `canvas-react/public/sketch/` 下的历史预览输出均被 Git 忽略。原有本地文件无需移动或删除。

后端单元测试会自行构造最小输入，不依赖这里的样本。需要完整画布验收时，启动工作台并导入你有权使用的设计文件。

部分历史命令行工具和 `npm --prefix canvas-react run sync:canvas` 默认读取 `fixtures/sketch/test_001/test/`；这些是可选的本地分析工具，不属于运行 Web 工作台的前置步骤。
