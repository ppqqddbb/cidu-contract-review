from enum import StrEnum


class JobType(StrEnum):
    PARSE_CONTRACT = "parse_contract"
    CLASSIFY_CONTRACT = "classify_contract"
    REVIEW_BATCH = "review_batch"
    SYNC_KNOWLEDGE = "sync_knowledge"
    GENERATE_REPORT = "generate_report"


class JobStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
