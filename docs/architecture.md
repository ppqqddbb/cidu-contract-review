# 架构摘要

运行链路：Tauri → FastAPI → PostgreSQL/文件存储 → PostgreSQL任务队列 → Worker → Dify → Python校验 → 人工复核 → 报告。

详细决策以`../../文件及需求分析/05-技术架构与模块划分.md`和`../../文件及需求分析/07-开发架构基线与工程规则.md`为准。
