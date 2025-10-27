"""Manages in-progress jobs and chunk accumulation."""

import io
import time
import zlib
from typing import Dict, List, Optional, Tuple
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
    expected_crc32: Optional[int] = None

    chunks: Dict[int, bytes] = field(default_factory=dict)
    total_chunks: Optional[int] = None
    received_chunks: int = 0

    # Timestamp tracking for timeout management
    created_at: float = field(default_factory=time.time)
    last_activity: float = field(default_factory=time.time)

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
            self.last_activity = time.time()
            logger.debug(
                "Chunk added",
                job_id=self.job_id,
                sequence=sequence,
                received=self.received_chunks,
                total=self.total_chunks
            )

    def age_seconds(self) -> float:
        """Get the age of this job in seconds."""
        return time.time() - self.created_at

    def idle_seconds(self) -> float:
        """Get the time since last activity in seconds."""
        return time.time() - self.last_activity

    def is_complete(self) -> bool:
        """Check if all chunks have been received."""
        if self.total_chunks is None:
            return False
        return self.received_chunks >= self.total_chunks

    def get_complete_data(self) -> bytes:
        """
        Reassemble all chunks into complete data and verify CRC32 checksum.

        Returns:
            Complete binary data

        Raises:
            ValueError: If job is incomplete or CRC32 verification fails
        """
        if not self.is_complete():
            raise ValueError(f"Job {self.job_id} is not complete")

        # Sort chunks by sequence and reassemble
        sorted_chunks = [self.chunks[i] for i in sorted(self.chunks.keys())]
        complete_data = reassemble_chunks(sorted_chunks)

        # Verify CRC32 checksum if provided
        if self.expected_crc32 is not None:
            actual_crc32 = zlib.crc32(complete_data) & 0xffffffff
            if actual_crc32 != self.expected_crc32:
                logger.error(
                    "CRC32 verification failed",
                    job_id=self.job_id,
                    expected_crc32=self.expected_crc32,
                    actual_crc32=actual_crc32
                )
                raise ValueError(
                    f"CRC32 checksum mismatch for job {self.job_id}: "
                    f"expected {self.expected_crc32}, got {actual_crc32}"
                )
            logger.info(
                "CRC32 verification passed",
                job_id=self.job_id,
                crc32=actual_crc32
            )

        return complete_data


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
            expected_crc32=message.crc32,
            total_chunks=message.total_chunks,
        )

        self._jobs[message.job_id] = job

        logger.info(
            "Job started",
            job_id=message.job_id,
            method=message.method,
            endpoint=message.endpoint,
            total_chunks=message.total_chunks,
            crc32=message.crc32
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

    def cleanup_stale_jobs(self, max_age_seconds: float) -> List[Tuple[str, str]]:
        """
        Clean up jobs that have exceeded the maximum age.

        Args:
            max_age_seconds: Maximum age in seconds before a job is considered stale

        Returns:
            List of (job_id, reason) tuples for cleaned up jobs
        """
        stale_jobs = []
        current_time = time.time()

        for job_id, job in list(self._jobs.items()):
            age = job.age_seconds()
            idle = job.idle_seconds()

            if age > max_age_seconds:
                stale_jobs.append((job_id, f"Job exceeded max age: {age:.1f}s > {max_age_seconds}s"))
                del self._jobs[job_id]
                logger.warning(
                    "Job cleaned up: exceeded max age",
                    job_id=job_id,
                    age_seconds=age,
                    max_age_seconds=max_age_seconds,
                    received_chunks=job.received_chunks,
                    total_chunks=job.total_chunks
                )

        return stale_jobs
