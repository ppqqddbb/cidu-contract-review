# 合同智审代码仓库协作规则

开发前必须依次阅读父目录：

1. `../文件及需求分析/04-开发功能点清单.md`
2. `../文件及需求分析/05-技术架构与模块划分.md`
3. `../文件及需求分析/06-合同分类知识文件三段式标准模板.md`
4. `../文件及需求分析/07-开发架构基线与工程规则.md`

固定边界：

- 单仓库、模块化单体；API与Worker分进程。
- Tauri只调用FastAPI，禁止直连PostgreSQL、Dify或模型。
- PostgreSQL是业务事实源和MVP持久化任务队列。
- Dify分类和审核Workflow必须分离。
- Dify HTTP调用只能位于`services/api/app/integrations/dify`。
- AI输出必须先通过Schema、枚举、引用、证据和版本校验。
- 数据库变更必须通过Alembic。
- 正式法律意见必须人工确认。
- MVP禁止开发账号、角色、菜单和权限。
- 先写验收条件和测试；实现保持最小、可验证、可回滚。

代码发现优先使用codebase-memory-mcp：`search_graph`、`trace_path`、`get_code_snippet`。仅在图谱不足、搜索字面量或非代码文件时回退到文本搜索。
