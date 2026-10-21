from datetime import UTC, datetime, timedelta

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from services.api.app.jobs.enums import JobStatus
from services.api.app.jobs.models import Job


class JobQueueRepository:
    async def claim_next(
        self,
        session: AsyncSession,
        *,
        worker_id: str,
        lease_seconds: int,
    ) -> Job | None:
        now = datetime.now(UTC)
        claimable = or_(
            Job.status == JobStatus.PENDING,
            and_(Job.status == JobStatus.RUNNING, Job.lease_until < now),
        )
        statement = (
            select(Job)
            .where(claimable, Job.available_at <= now, Job.attempt < Job.max_attempts)
            .order_by(Job.priority.desc(), Job.created_at.asc())
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        job = await session.scalar(statement)
        if job is None:
            return None

        job.status = JobStatus.RUNNING
        job.worker_id = worker_id
        job.lease_until = now + timedelta(seconds=lease_seconds)
        job.attempt += 1
        await session.flush()
        return job
