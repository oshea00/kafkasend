"""Main portal service that bridges Kafka to REST API."""

import json
import signal
import sys
from typing import Optional
from kafka import KafkaConsumer, KafkaProducer
import structlog

from kafkasend.common.models import (
    KafkaRequestMessage,
    KafkaResponseMessage,
    MessageType,
)
from kafkasend.common.config import KafkaConfig, OAuth2Config, PortalConfig
from kafkasend.common.logging import configure_logging
from kafkasend.common.chunking import encode_chunk, MAX_CHUNK_SIZE
from kafkasend.portal.job_manager import JobManager
from kafkasend.portal.rest_client import RestApiClient

logger = structlog.get_logger(__name__)


class PortalService:
    """Main service that bridges Kafka messages to REST API."""

    def __init__(
        self,
        kafka_config: KafkaConfig,
        portal_config: PortalConfig,
        oauth_config: Optional[OAuth2Config] = None
    ):
        """
        Initialize the portal service.

        Args:
            kafka_config: Kafka configuration
            portal_config: Portal configuration
            oauth_config: OAuth2 configuration (optional)
        """
        self.kafka_config = kafka_config
        self.portal_config = portal_config

        self.job_manager = JobManager(
            max_concurrent_jobs=portal_config.max_concurrent_jobs
        )
        self.rest_client = RestApiClient(portal_config, oauth_config)

        self._running = False
        self._consumer: Optional[KafkaConsumer] = None
        self._producer: Optional[KafkaProducer] = None

    def start(self) -> None:
        """Start the portal service."""
        logger.info("Starting portal service")

        # Setup signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

        # Initialize Kafka consumer
        self._consumer = KafkaConsumer(
            self.kafka_config.request_topic,
            bootstrap_servers=self.kafka_config.bootstrap_servers.split(','),
            group_id=self.kafka_config.consumer_group,
            auto_offset_reset=self.kafka_config.auto_offset_reset,
            value_deserializer=lambda m: json.loads(m.decode('utf-8')),
            session_timeout_ms=self.kafka_config.session_timeout_ms,
            max_poll_records=self.kafka_config.max_poll_records,
        )

        # Initialize Kafka producer
        self._producer = KafkaProducer(
            bootstrap_servers=self.kafka_config.bootstrap_servers.split(','),
            value_serializer=lambda v: json.dumps(v).encode('utf-8'),
            max_request_size=1048576,  # 1MB - Kafka default max message size
        )

        logger.info(
            "Kafka connections established",
            request_topic=self.kafka_config.request_topic,
            response_topic=self.kafka_config.response_topic
        )

        self._running = True
        self._run()

    def _run(self) -> None:
        """Main event loop."""
        logger.info("Portal service running, waiting for messages...")

        while self._running:
            try:
                # Poll for messages
                messages = self._consumer.poll(timeout_ms=1000)

                for topic_partition, records in messages.items():
                    for record in records:
                        self._handle_message(record.value)

            except Exception as e:
                logger.error("Error in main loop", error=str(e), exc_info=True)

        self.stop()

    def _handle_message(self, message_data: dict) -> None:
        """
        Handle an incoming Kafka message.

        Args:
            message_data: Deserialized message data
        """
        try:
            message = KafkaRequestMessage(**message_data)

            logger.debug(
                "Message received",
                job_id=message.job_id,
                message_type=message.message_type,
                sequence=message.sequence
            )

            if message.message_type == MessageType.START:
                self._handle_start(message)
            elif message.message_type == MessageType.CHUNK:
                self._handle_chunk(message)
            elif message.message_type == MessageType.END:
                self._handle_end(message)
            else:
                logger.warning("Unknown message type", message_type=message.message_type)

        except Exception as e:
            logger.error(
                "Error handling message",
                error=str(e),
                message_data=message_data,
                exc_info=True
            )
            # Try to send error response if we have a job_id
            if isinstance(message_data, dict) and 'job_id' in message_data:
                self._send_error_response(message_data['job_id'], str(e))

    def _handle_start(self, message: KafkaRequestMessage) -> None:
        """Handle START message."""
        try:
            job = self.job_manager.start_job(message)

            # If no chunks expected (total_chunks == 0), execute immediately
            if message.total_chunks == 0:
                self._execute_and_respond(job)

        except Exception as e:
            logger.error("Error starting job", job_id=message.job_id, error=str(e))
            self._send_error_response(message.job_id, str(e))

    def _handle_chunk(self, message: KafkaRequestMessage) -> None:
        """Handle CHUNK message."""
        try:
            completed_job = self.job_manager.add_chunk(message)

            # If job is complete after this chunk, execute request
            if completed_job:
                self._execute_and_respond(completed_job)

        except Exception as e:
            logger.error("Error handling chunk", job_id=message.job_id, error=str(e))
            self._send_error_response(message.job_id, str(e))
            # Cancel the job
            self.job_manager.cancel_job(message.job_id)

    def _handle_end(self, message: KafkaRequestMessage) -> None:
        """Handle END message - marks completion without data."""
        try:
            job = self.job_manager.get_job(message.job_id)
            if job and job.is_complete():
                self._execute_and_respond(job)
            elif job:
                logger.warning(
                    "Received END but job not complete",
                    job_id=message.job_id,
                    received=job.received_chunks,
                    total=job.total_chunks
                )
        except Exception as e:
            logger.error("Error handling end", job_id=message.job_id, error=str(e))
            self._send_error_response(message.job_id, str(e))

    def _execute_and_respond(self, job) -> None:
        """Execute REST request and send response back to Kafka."""
        try:
            # Execute REST request
            response = self.rest_client.execute_request(job)

            # Send response back to Kafka
            self._send_response(job.job_id, response)

            # Complete the job
            self.job_manager.complete_job(job.job_id)

        except Exception as e:
            logger.error(
                "Error executing request",
                job_id=job.job_id,
                error=str(e)
            )
            self._send_error_response(job.job_id, str(e))
            self.job_manager.cancel_job(job.job_id)

    def _send_response(self, job_id: str, response) -> None:
        """
        Send HTTP response back to Kafka response topic.

        Args:
            job_id: Job identifier
            response: HTTP response object
        """
        # Check if response is JSON
        is_json = False
        response_data = response.content

        content_type = response.headers.get('Content-Type', '')
        if 'application/json' in content_type:
            is_json = True
            # For JSON, send as text
            response_text = response.text
        else:
            # For binary, encode as base64
            response_text = encode_chunk(response_data)

        # Check if we need to chunk the response
        response_size = len(response_text)
        needs_chunking = response_size > MAX_CHUNK_SIZE

        if needs_chunking:
            # Send response in chunks
            total_chunks = (response_size + MAX_CHUNK_SIZE - 1) // MAX_CHUNK_SIZE

            for i in range(total_chunks):
                start = i * MAX_CHUNK_SIZE
                end = min(start + MAX_CHUNK_SIZE, response_size)
                chunk_data = response_text[start:end]

                message = KafkaResponseMessage(
                    job_id=job_id,
                    message_type=MessageType.CHUNK,
                    sequence=i,
                    total_chunks=total_chunks,
                    status_code=response.status_code if i == 0 else None,
                    headers=dict(response.headers) if i == 0 else None,
                    data=chunk_data,
                    is_json=is_json
                )

                self._send_kafka_message(message)

            logger.info(
                "Response sent in chunks",
                job_id=job_id,
                total_chunks=total_chunks
            )
        else:
            # Send single response message
            message = KafkaResponseMessage(
                job_id=job_id,
                message_type=MessageType.START,
                status_code=response.status_code,
                headers=dict(response.headers),
                data=response_text,
                is_json=is_json,
                total_chunks=1
            )

            self._send_kafka_message(message)

            logger.info("Response sent", job_id=job_id, status_code=response.status_code)

    def _send_error_response(self, job_id: str, error_message: str) -> None:
        """
        Send error response to Kafka.

        Args:
            job_id: Job identifier
            error_message: Error description
        """
        message = KafkaResponseMessage(
            job_id=job_id,
            message_type=MessageType.ERROR,
            error_message=error_message
        )

        self._send_kafka_message(message)
        logger.info("Error response sent", job_id=job_id)

    def _send_kafka_message(self, message: KafkaResponseMessage) -> None:
        """
        Send a message to Kafka response topic.

        Args:
            message: Response message to send
        """
        if not self._producer:
            raise RuntimeError("Producer not initialized")

        self._producer.send(
            self.kafka_config.response_topic,
            value=message.model_dump()
        )
        self._producer.flush()

    def _signal_handler(self, signum, frame) -> None:
        """Handle shutdown signals."""
        logger.info("Shutdown signal received", signal=signum)
        self._running = False

    def stop(self) -> None:
        """Stop the portal service."""
        logger.info("Stopping portal service")

        if self._consumer:
            self._consumer.close()
            logger.info("Kafka consumer closed")

        if self._producer:
            self._producer.close()
            logger.info("Kafka producer closed")

        logger.info("Portal service stopped")


def main() -> None:
    """Main entry point for the portal service."""
    # Load configuration
    kafka_config = KafkaConfig()
    portal_config = PortalConfig()

    # Configure logging
    configure_logging(portal_config.log_level)

    logger.info("Portal service configuration loaded")

    # Load OAuth config if needed
    oauth_config = None
    if portal_config.use_oauth:
        try:
            oauth_config = OAuth2Config()
            logger.info("OAuth2 configuration loaded")
        except Exception as e:
            logger.error("Failed to load OAuth2 configuration", error=str(e))
            sys.exit(1)

    # Create and start service
    service = PortalService(kafka_config, portal_config, oauth_config)

    try:
        service.start()
    except Exception as e:
        logger.error("Fatal error in portal service", error=str(e), exc_info=True)
        sys.exit(1)


if __name__ == '__main__':
    main()
