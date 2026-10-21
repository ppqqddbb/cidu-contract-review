import asyncio
import socket
from datetime import UTC, datetime

import structlog

from services.api.app.core.config import get_settings
from services.api.app.core.logging import configure_logging


async def run_worker() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    logger = structlog.get_logger(service="worker", environment=settings.environment)
    worker_id = f"{socket.gethostname()}-{id(asyncio.current_task())}"
    logger.info(
        "worker_started",
        worker_id=worker_id,
        poll_interval_seconds=settings.worker_poll_interval_seconds,
        started_at=datetime.now(UTC).isoformat(),
    )

    # 任务领取和 handler 分发将在首条纵向业务链路中接入。
    # 骨架阶段只保持独立进程边界，不轮询数据库，也不伪造任务成功结果。
    stop_event = asyncio.Event()
    await stop_event.wait()


def main() -> None:
    try:
        asyncio.run(run_worker())
    except KeyboardInterrupt:
        return


if __name__ == "__main__":
    main()
