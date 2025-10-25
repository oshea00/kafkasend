"""Tests for data models."""

from kafkasend.common.models import (
    KafkaRequestMessage,
    KafkaResponseMessage,
    MessageType,
    HttpMethod,
)


def test_kafka_request_message_creation():
    """Test creating a Kafka request message."""
    msg = KafkaRequestMessage(
        job_id="test-123",
        message_type=MessageType.START,
        sequence=0,
        total_chunks=5,
        method=HttpMethod.POST,
        endpoint="/api/upload",
        headers={"Authorization": "Bearer token"},
        filename="test.pdf",
        content_type="application/pdf"
    )

    assert msg.job_id == "test-123"
    assert msg.message_type == MessageType.START
    assert msg.method == HttpMethod.POST
    assert msg.endpoint == "/api/upload"
    assert msg.filename == "test.pdf"


def test_kafka_response_message_creation():
    """Test creating a Kafka response message."""
    msg = KafkaResponseMessage(
        job_id="test-456",
        message_type=MessageType.START,
        status_code=200,
        headers={"Content-Type": "application/json"},
        data='{"result": "success"}',
        is_json=True,
        total_chunks=1
    )

    assert msg.job_id == "test-456"
    assert msg.status_code == 200
    assert msg.is_json is True
    assert msg.total_chunks == 1


def test_message_serialization():
    """Test message serialization to dict."""
    msg = KafkaRequestMessage(
        job_id="test-789",
        message_type=MessageType.CHUNK,
        sequence=1,
        data="base64data"
    )

    # Convert to dict
    msg_dict = msg.model_dump()

    assert msg_dict["job_id"] == "test-789"
    assert msg_dict["message_type"] == "CHUNK"
    assert msg_dict["sequence"] == 1
    assert msg_dict["data"] == "base64data"


def test_error_message():
    """Test creating an error response message."""
    msg = KafkaResponseMessage(
        job_id="test-error",
        message_type=MessageType.ERROR,
        error_message="Something went wrong"
    )

    assert msg.message_type == MessageType.ERROR
    assert msg.error_message == "Something went wrong"
