from services.api.app.jobs.enums import JobStatus, JobType


def test_job_types_cover_mvp_long_running_work() -> None:
    assert {job_type.value for job_type in JobType} == {
        "parse_contract",
        "classify_contract",
        "review_batch",
        "sync_knowledge",
        "generate_report",
    }
    assert JobStatus.PENDING.value == "pending"
