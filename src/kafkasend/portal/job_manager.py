"""Manages in-progress jobs and chunk accumulation."""

import io
from typing import Dict, List, Optional
from dataclasses import dataclass, field
import structlog

from kafkasend.common.models import KafkaRequestMessage, HttpMethod
from kafkasend.common.chunking import decode_chunk, reassemble_chunks

logger = structlog.get_logger(__name__)


@dataclass
class JobState:
    """State of an in-progress job."""

    job_id: str
    method: HttpMethod
    endpoint: str
    headers: Dict[str, str] = field(default_factory=dict)
    filename: Optional[str] = None
    content_type: Optional[str] = None

    chunks: Dict[int, bytes] = field(default_factory=dict)
    total_chunks: Optional[int] = None
    received_chunks: int = 0

    def add_chunk(self, sequence: int, data: bytes) -> None:
        """
        Add a chunk to the job.

        Args:
            sequence: Chunk sequence number
            data: Binary chunk data
        """
        if sequence not in self.chunks:
            self.chunks[sequence] = data
            self.received_chunks += 1
            logger.debug(
                "Chunk added",
                job_id=self.job_id,
                sequence=sequence,
                received=self.received_chunks,
                total=self.total_chunks
            )

    def is_complete(self) -> bool:
        """Check if all chunks have been received."""
        if self.total_chunks is None:
            return False
        return self.received_chunks >= self.total_chunks

    def get_complete_data(self) -> bytes:
        """
        Reassemble all chunks into complete data.

        Returns:
            Complete binary data
        """
        if not self.is_complete():
            raise ValueError(f"Job {self.job_id} is not complete")

        # Sort chunks by sequence and reassemble
        sorted_chunks = [self.chunks[i] for i in sorted(self.chunks.keys())]
        return reassemble_chunks(sorted_chunks)


class JobManager:
    """Manages multiple in-progress jobs."""

    def __init__(self, max_concurrent_jobs: int = 10):
        """
        Initialize the job manager.

        Args:
            max_concurrent_jobs: Maximum number of concurrent jobs
        """
        self.max_concurrent_jobs = max_concurrent_jobs
        self._jobs: Dict[str, JobState] = {}

    def start_job(self, message: KafkaRequestMessage) -> JobState:
        """
        Start a new job from a START message.

        Args:
            message: START message with job details

        Returns:
            New job state

        Raises:
            ValueError: If job already exists or required fields are missing
        """
        if message.job_id in self._jobs:
            raise ValueError(f"Job {message.job_id} already exists")

        if len(self._jobs) >= self.max_concurrent_jobs:
            raise RuntimeError(
                f"Maximum concurrent jobs ({self.max_concurrent_jobs}) reached"
            )

        if not message.method or not message.endpoint:
            raise ValueError("START message must include method and endpoint")

        job = JobState(
            job_id=message.job_id,
            method=message.method,
            endpoint=message.endpoint,
            headers=message.headers or {},
            filename=message.filename,
            content_type=message.content_type,
            total_chunks=message.total_chunks,
        )

        self._jobs[message.job_id] = job

        logger.info(
            "Job started",
            job_id=message.job_id,
            method=message.method,
            endpoint=message.endpoint,
            total_chunks=message.total_chunks
        )

        return job

    def add_chunk(self, message: KafkaRequestMessage) -> Optional[JobState]:
        """
        Add a chunk to an existing job.

        Args:
            message: CHUNK message with data

        Returns:
            Job state if complete, None otherwise

        Raises:
            ValueError: If job doesn't exist or data is missing
        """
        if message.job_id not in self._jobs:
            raise ValueError(f"Job {message.job_id} not found")

        if not message.data:
            raise ValueError("CHUNK message must include data")

        job = self._jobs[message.job_id]

        # Decode and add chunk
        chunk_data = decode_chunk(message.data)
        job.add_chunk(message.sequence, chunk_data)

        # Return job if complete
        if job.is_complete():
            logger.info("Job complete, all chunks received", job_id=message.job_id)
            return job

        return None

    def complete_job(self, job_id: str) -> JobState:
        """
        Mark a job as complete and remove from active jobs.

        Args:
            job_id: Job identifier

        Returns:
            Completed job state

        Raises:
            ValueError: If job doesn't exist
        """
        if job_id not in self._jobs:
            raise ValueError(f"Job {job_id} not found")

        job = self._jobs.pop(job_id)
        logger.info("Job completed and removed", job_id=job_id)
        return job

    def get_job(self, job_id: str) -> Optional[JobState]:
        """
        Get job state by ID.

        Args:
            job_id: Job identifier

        Returns:
            Job state if found, None otherwise
        """
        return self._jobs.get(job_id)

    def cancel_job(self, job_id: str) -> None:
        """
        Cancel and remove a job.

        Args:
            job_id: Job identifier
        """
        if job_id in self._jobs:
            del self._jobs[job_id]
            logger.info("Job cancelled", job_id=job_id)

    def get_active_job_count(self) -> int:
        """Get the number of active jobs."""
        return len(self._jobs)
