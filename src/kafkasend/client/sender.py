"""Client for sending files and requests to Kafka."""

import json
import os
import uuid
import zlib
from typing import Dict, Optional
from kafka import KafkaProducer
import structlog

from kafkasend.common.models import (
    KafkaRequestMessage,
    MessageType,
    HttpMethod,
)
from kafkasend.common.chunking import chunk_file, encode_chunk, calculate_chunk_count
from kafkasend.common.config import KafkaConfig

logger = structlog.get_logger(__name__)


class KafkaSender:
    """Client for sending requests to Kafka."""

    def __init__(self, kafka_config: KafkaConfig):
        """
        Initialize the Kafka sender.

        Args:
            kafka_config: Kafka configuration
        """
        self.kafka_config = kafka_config

        self._producer = KafkaProducer(
            bootstrap_servers=kafka_config.bootstrap_servers.split(','),
            value_serializer=lambda v: json.dumps(v).encode('utf-8'),
            max_request_size=1048576,  # 1MB - Kafka default max message size
        )

        logger.info(
            "Kafka producer initialized",
            bootstrap_servers=kafka_config.bootstrap_servers
        )

    def send_file(
        self,
        file_path: str,
        endpoint: str,
        method: HttpMethod = HttpMethod.POST,
        headers: Optional[Dict[str, str]] = None,
        content_type: Optional[str] = None,
        job_id: Optional[str] = None
    ) -> str:
        """
        Send a file via Kafka to be posted to REST API.

        Args:
            file_path: Path to the file to send
            endpoint: Target API endpoint
            method: HTTP method
            headers: Additional HTTP headers
            content_type: Content type of the file
            job_id: Optional job ID (generated if not provided)

        Returns:
            Job ID for tracking the request
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")

        # Generate job ID if not provided
        if not job_id:
            job_id = str(uuid.uuid4())

        filename = os.path.basename(file_path)
        file_size = os.path.getsize(file_path)

        # Detect content type if not provided
        if not content_type:
            content_type = self._detect_content_type(filename)

        # Calculate total chunks
        total_chunks = calculate_chunk_count(file_path)

        # Calculate CRC32 checksum of complete file
        file_crc32 = self._calculate_file_crc32(file_path)

        logger.info(
            "Starting file upload",
            job_id=job_id,
            file_path=file_path,
            file_size=file_size,
            total_chunks=total_chunks,
            endpoint=endpoint,
            crc32=file_crc32
        )

        # Send START message
        start_message = KafkaRequestMessage(
            job_id=job_id,
            message_type=MessageType.START,
            sequence=0,
            total_chunks=total_chunks,
            method=method,
            endpoint=endpoint,
            headers=headers or {},
            filename=filename,
            content_type=content_type,
            crc32=file_crc32
        )

        self._send_message(start_message)
        logger.info("START message sent", job_id=job_id)

        # Send file chunks
        for i, chunk in enumerate(chunk_file(file_path)):
            encoded_chunk = encode_chunk(chunk)

            chunk_message = KafkaRequestMessage(
                job_id=job_id,
                message_type=MessageType.CHUNK,
                sequence=i,
                total_chunks=total_chunks,
                data=encoded_chunk
            )

            self._send_message(chunk_message)

            if (i + 1) % 10 == 0:
                logger.info(
                    "Progress",
                    job_id=job_id,
                    chunks_sent=i + 1,
                    total_chunks=total_chunks
                )

        logger.info(
            "File upload complete",
            job_id=job_id,
            total_chunks=total_chunks
        )

        return job_id

    def send_request(
        self,
        endpoint: str,
        method: HttpMethod = HttpMethod.GET,
        headers: Optional[Dict[str, str]] = None,
        job_id: Optional[str] = None
    ) -> str:
        """
        Send a simple HTTP request (no body) via Kafka.

        Args:
            endpoint: Target API endpoint
            method: HTTP method
            headers: HTTP headers
            job_id: Optional job ID (generated if not provided)

        Returns:
            Job ID for tracking the request
        """
        if not job_id:
            job_id = str(uuid.uuid4())

        logger.info(
            "Sending request",
            job_id=job_id,
            method=method,
            endpoint=endpoint
        )

        # Send START message with no chunks
        start_message = KafkaRequestMessage(
            job_id=job_id,
            message_type=MessageType.START,
            sequence=0,
            total_chunks=0,
            method=method,
            endpoint=endpoint,
            headers=headers or {}
        )

        self._send_message(start_message)

        logger.info("Request sent", job_id=job_id)

        return job_id

    def _send_message(self, message: KafkaRequestMessage) -> None:
        """
        Send a message to Kafka.

        Args:
            message: Request message to send
        """
        # Use job_id as partition key to ensure all messages for the same job
        # go to the same partition (and thus the same portal instance)
        self._producer.send(
            self.kafka_config.request_topic,
            key=message.job_id.encode('utf-8'),
            value=message.model_dump()
        )
        self._producer.flush()

    def _detect_content_type(self, filename: str) -> str:
        """
        Detect content type from filename extension.

        Args:
            filename: Name of the file

        Returns:
            Content type string
        """
        ext = os.path.splitext(filename)[1].lower()

        content_types = {
            '.pdf': 'application/pdf',
            '.doc': 'application/msword',
            '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            '.xls': 'application/vnd.ms-excel',
            '.xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
            '.png': 'image/png',
            '.gif': 'image/gif',
            '.txt': 'text/plain',
            '.json': 'application/json',
            '.xml': 'application/xml',
            '.zip': 'application/zip',
        }

        return content_types.get(ext, 'application/octet-stream')

    def _calculate_file_crc32(self, file_path: str) -> int:
        """
        Calculate CRC32 checksum of a file.

        Args:
            file_path: Path to the file

        Returns:
            CRC32 checksum as unsigned 32-bit integer
        """
        crc = 0
        with open(file_path, 'rb') as f:
            while chunk := f.read(65536):  # Read in 64KB chunks
                crc = zlib.crc32(chunk, crc)

        # Ensure unsigned 32-bit integer
        return crc & 0xffffffff

    def close(self) -> None:
        """Close the Kafka producer."""
        self._producer.close()
        logger.info("Kafka producer closed")
