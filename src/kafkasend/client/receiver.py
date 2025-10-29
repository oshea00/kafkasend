"""Client for receiving responses from Kafka."""

import json
import zlib
from typing import Dict, List, Optional, Callable
from kafka import KafkaConsumer
import structlog

from kafkasend.common.models import KafkaResponseMessage, MessageType
from kafkasend.common.chunking import decode_chunk, reassemble_chunks
from kafkasend.common.config import KafkaConfig

logger = structlog.get_logger(__name__)


class ResponseState:
    """State for accumulating response chunks."""

    def __init__(self, job_id: str):
        self.job_id = job_id
        self.chunks: Dict[int, str] = {}
        self.total_chunks: Optional[int] = None
        self.status_code: Optional[int] = None
        self.headers: Optional[Dict[str, str]] = None
        self.is_json: bool = False
        self.expected_crc32: Optional[int] = None
        self.error_message: Optional[str] = None

    def add_chunk(self, sequence: int, data: str) -> None:
        """Add a chunk to the response."""
        self.chunks[sequence] = data

    def is_complete(self) -> bool:
        """Check if all chunks have been received."""
        if self.total_chunks is None:
            return False
        return len(self.chunks) >= self.total_chunks

    def get_complete_data(self) -> str:
        """
        Get the reassembled response data and verify CRC32 checksum.

        Returns:
            Complete response data

        Raises:
            ValueError: If response is incomplete or CRC32 verification fails
        """
        if not self.is_complete():
            raise ValueError(f"Response for job {self.job_id} is not complete")

        # Sort chunks by sequence and concatenate
        sorted_data = [self.chunks[i] for i in sorted(self.chunks.keys())]
        complete_data = ''.join(sorted_data)

        # Verify CRC32 checksum if provided
        if self.expected_crc32 is not None:
            # Calculate CRC32 of the raw bytes
            if self.is_json:
                # For JSON, calculate CRC32 of UTF-8 encoded text
                raw_bytes = complete_data.encode('utf-8')
            else:
                # For binary data, decode base64 first
                import base64
                raw_bytes = base64.b64decode(complete_data)

            actual_crc32 = zlib.crc32(raw_bytes) & 0xffffffff

            if actual_crc32 != self.expected_crc32:
                logger.error(
                    "CRC32 verification failed",
                    job_id=self.job_id,
                    expected_crc32=self.expected_crc32,
                    actual_crc32=actual_crc32
                )
                raise ValueError(
                    f"CRC32 checksum mismatch for response {self.job_id}: "
                    f"expected {self.expected_crc32}, got {actual_crc32}"
                )

            logger.info(
                "CRC32 verification passed",
                job_id=self.job_id,
                crc32=actual_crc32
            )

        return complete_data


class KafkaReceiver:
    """Client for receiving responses from Kafka."""

    def __init__(self, kafka_config: KafkaConfig, consumer_group: Optional[str] = None):
        """
        Initialize the Kafka receiver.

        Args:
            kafka_config: Kafka configuration
            consumer_group: Consumer group ID (generated if not provided)
        """
        self.kafka_config = kafka_config

        if not consumer_group:
            import uuid
            consumer_group = f"kafkasend-client-{uuid.uuid4().hex[:8]}"

        self._consumer = KafkaConsumer(
            kafka_config.response_topic,
            bootstrap_servers=kafka_config.bootstrap_servers.split(','),
            group_id=consumer_group,
            auto_offset_reset='latest',  # Only read new messages
            value_deserializer=lambda m: json.loads(m.decode('utf-8')),
        )

        self._responses: Dict[str, ResponseState] = {}

        logger.info(
            "Kafka consumer initialized",
            topic=kafka_config.response_topic,
            consumer_group=consumer_group
        )

    def wait_for_response(
        self,
        job_id: str,
        timeout_ms: int = 300000,
        callback: Optional[Callable[[ResponseState], None]] = None
    ) -> ResponseState:
        """
        Wait for a complete response for a specific job.

        Args:
            job_id: Job ID to wait for
            timeout_ms: Timeout in milliseconds
            callback: Optional callback for progress updates

        Returns:
            Complete response state

        Raises:
            TimeoutError: If timeout is reached
        """
        logger.info("Waiting for response", job_id=job_id, timeout_ms=timeout_ms)

        while True:
            messages = self._consumer.poll(timeout_ms=1000)

            for topic_partition, records in messages.items():
                for record in records:
                    response = KafkaResponseMessage(**record.value)

                    if response.job_id == job_id:
                        state = self._process_response(response)

                        if callback:
                            callback(state)

                        if state.error_message:
                            logger.error(
                                "Error response received",
                                job_id=job_id,
                                error=state.error_message
                            )
                            return state

                        if state.is_complete():
                            logger.info("Complete response received", job_id=job_id)
                            return state

            # Check timeout
            timeout_ms -= 1000
            if timeout_ms <= 0:
                raise TimeoutError(f"Timeout waiting for response for job {job_id}")

    def _process_response(self, response: KafkaResponseMessage) -> ResponseState:
        """
        Process a response message.

        Args:
            response: Response message

        Returns:
            Updated response state
        """
        job_id = response.job_id

        # Get or create state
        if job_id not in self._responses:
            self._responses[job_id] = ResponseState(job_id)

        state = self._responses[job_id]

        # Handle error
        if response.message_type == MessageType.ERROR:
            state.error_message = response.error_message
            return state

        # Update state from first message
        if response.status_code is not None:
            state.status_code = response.status_code
        if response.headers is not None:
            state.headers = response.headers
        if response.total_chunks is not None:
            state.total_chunks = response.total_chunks
        if response.crc32 is not None:
            state.expected_crc32 = response.crc32

        state.is_json = response.is_json

        # Add chunk data
        if response.data:
            state.add_chunk(response.sequence, response.data)

        logger.debug(
            "Response chunk processed",
            job_id=job_id,
            sequence=response.sequence,
            chunks_received=len(state.chunks),
            total_chunks=state.total_chunks
        )

        return state

    def close(self) -> None:
        """Close the Kafka consumer."""
        self._consumer.close()
        logger.info("Kafka consumer closed")
