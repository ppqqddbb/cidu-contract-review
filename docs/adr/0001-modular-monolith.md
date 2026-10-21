# ADR-0001：模块化单体与API/Worker分进程

- 状态：已接受
- 日期：2026-07-10

## 决策

采用单仓库模块化单体。FastAPI负责同步业务API，独立Worker负责长任务，PostgreSQL同时承担业务事实源和MVP持久化任务队列。

## 原因

MVP周期短，业务边界仍在稳定；该方案减少部署组件，同时保留进程隔离、可靠重试和未来拆分空间。

## 后果

禁止在MVP引入微服务、Redis/Celery或Kafka；禁止使用FastAPI BackgroundTasks执行完整审核。
