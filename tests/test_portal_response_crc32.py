"""Tests for portal's response CRC32 calculation logic."""

import json
import zlib
from unittest.mock import Mock, MagicMock
import pytest

from kafkasend.common.models import MessageType
from kafkasend.common.config import KafkaConfig, PortalConfig
from kafkasend.portal.service import PortalService
from kafkasend.common.chunking import encode_chunk


def test_portal_json_response_crc32():
    """Test portal correctly calculates CRC32 for JSON response."""
    # Create portal service with mocked Kafka
    kafka_config = KafkaConfig()
    portal_config = PortalConfig(target_api_url="http://localhost:8080")
    service = PortalService(kafka_config, portal_config, oauth_config=None)

    # Mock the Kafka producer to capture messages
    service._producer = MagicMock()
    sent_messages = []

    def capture_send(topic, key, value):
        sent_messages.append(value)

    service._producer.send.side_effect = capture_send
    service._producer.flush = MagicMock()

    # Mock HTTP response with JSON data
    json_data = '{"status": "success", "id": 12345}'
    json_bytes = json_data.encode('utf-8')
    expected_crc32 = zlib.crc32(json_bytes) & 0xffffffff

    mock_response = Mock()
    mock_response.content = json_bytes
    mock_response.text = json_data
    mock_response.status_code = 200
    mock_response.headers = {'Content-Type': 'application/json'}

    # Call _send_response
    job_id = "test-json-job"
    service._send_response(job_id, mock_response)

    # Verify message was sent with correct CRC32
    assert len(sent_messages) == 1
    response_msg = sent_messages[0]

    assert response_msg['job_id'] == job_id
    assert response_msg['status_code'] == 200
    assert response_msg['is_json'] is True
    assert response_msg['crc32'] == expected_crc32
    assert response_msg['data'] == json_data


def test_portal_binary_response_crc32():
    """Test portal correctly calculates CRC32 for binary response."""
    # Create portal service with mocked Kafka
    kafka_config = KafkaConfig()
    portal_config = PortalConfig(target_api_url="http://localhost:8080")
    service = PortalService(kafka_config, portal_config, oauth_config=None)

    # Mock the Kafka producer
    service._producer = MagicMock()
    sent_messages = []

    def capture_send(topic, key, value):
        sent_messages.append(value)

    service._producer.send.side_effect = capture_send
    service._producer.flush = MagicMock()

    # Mock HTTP response with binary data
    binary_data = b"Binary file content \x00\x01\x02\xFF\xFE"
    expected_crc32 = zlib.crc32(binary_data) & 0xffffffff

    mock_response = Mock()
    mock_response.content = binary_data
    mock_response.status_code = 200
    mock_response.headers = {'Content-Type': 'application/octet-stream'}

    # Call _send_response
    job_id = "test-binary-job"
    service._send_response(job_id, mock_response)

    # Verify message was sent with correct CRC32
    assert len(sent_messages) == 1
    response_msg = sent_messages[0]

    assert response_msg['job_id'] == job_id
    assert response_msg['status_code'] == 200
    assert response_msg['is_json'] is False
    assert response_msg['crc32'] == expected_crc32
    # Data should be base64 encoded
    assert response_msg['data'] == encode_chunk(binary_data)


def test_portal_large_response_crc32():
    """Test portal correctly calculates CRC32 for large chunked response."""
    # Create portal service with mocked Kafka
    kafka_config = KafkaConfig()
    portal_config = PortalConfig(target_api_url="http://localhost:8080")
    service = PortalService(kafka_config, portal_config, oauth_config=None)

    # Mock the Kafka producer
    service._producer = MagicMock()
    sent_messages = []

    def capture_send(topic, key, value):
        sent_messages.append(value)

    service._producer.send.side_effect = capture_send
    service._producer.flush = MagicMock()

    # Create large binary data that requires chunking (> 650KB)
    large_data = b"X" * 700000  # 700KB
    expected_crc32 = zlib.crc32(large_data) & 0xffffffff

    mock_response = Mock()
    mock_response.content = large_data
    mock_response.status_code = 200
    mock_response.headers = {'Content-Type': 'application/octet-stream'}

    # Call _send_response
    job_id = "test-large-job"
    service._send_response(job_id, mock_response)

    # Verify multiple messages were sent (START + CHUNKs)
    assert len(sent_messages) > 1, "Large response should be chunked"

    # Verify first message is START with metadata only (no data)
    start_msg = sent_messages[0]
    assert start_msg['job_id'] == job_id
    assert start_msg['message_type'] == MessageType.START.value
    assert start_msg['sequence'] == 0
    assert start_msg['crc32'] == expected_crc32
    assert start_msg['status_code'] == 200
    assert start_msg['data'] is None  # START message has no data for multi-chunk

    # Verify subsequent messages are CHUNKs with data only (no metadata)
    for i, chunk in enumerate(sent_messages[1:], start=0):
        assert chunk['job_id'] == job_id
        assert chunk['message_type'] == MessageType.CHUNK.value
        assert chunk['sequence'] == i
        assert chunk['crc32'] is None  # Only START has CRC32
        assert chunk['status_code'] is None  # Only START has status_code
        assert chunk['data'] is not None  # CHUNKs have data


def test_portal_pdf_response_crc32():
    """Test portal correctly calculates CRC32 for PDF binary response."""
    # Create portal service with mocked Kafka
    kafka_config = KafkaConfig()
    portal_config = PortalConfig(target_api_url="http://localhost:8080")
    service = PortalService(kafka_config, portal_config, oauth_config=None)

    # Mock the Kafka producer
    service._producer = MagicMock()
    sent_messages = []

    def capture_send(topic, key, value):
        sent_messages.append(value)

    service._producer.send.side_effect = capture_send
    service._producer.flush = MagicMock()

    # Mock PDF binary data (simplified PDF header)
    pdf_data = b"%PDF-1.4\n%\xE2\xE3\xCF\xD3\n" + b"PDF content here..." * 100
    expected_crc32 = zlib.crc32(pdf_data) & 0xffffffff

    mock_response = Mock()
    mock_response.content = pdf_data
    mock_response.status_code = 200
    mock_response.headers = {'Content-Type': 'application/pdf'}

    # Call _send_response
    job_id = "test-pdf-job"
    service._send_response(job_id, mock_response)

    # Verify message was sent with correct CRC32
    assert len(sent_messages) == 1
    response_msg = sent_messages[0]

    assert response_msg['job_id'] == job_id
    assert response_msg['status_code'] == 200
    assert response_msg['is_json'] is False  # PDF is not JSON
    assert response_msg['crc32'] == expected_crc32


def test_portal_empty_response_crc32():
    """Test portal correctly handles empty response."""
    # Create portal service with mocked Kafka
    kafka_config = KafkaConfig()
    portal_config = PortalConfig(target_api_url="http://localhost:8080")
    service = PortalService(kafka_config, portal_config, oauth_config=None)

    # Mock the Kafka producer
    service._producer = MagicMock()
    sent_messages = []

    def capture_send(topic, key, value):
        sent_messages.append(value)

    service._producer.send.side_effect = capture_send
    service._producer.flush = MagicMock()

    # Mock empty response
    empty_data = b""
    expected_crc32 = zlib.crc32(empty_data) & 0xffffffff  # CRC32 of empty data

    mock_response = Mock()
    mock_response.content = empty_data
    mock_response.text = ""
    mock_response.status_code = 204  # No Content
    mock_response.headers = {'Content-Type': 'text/plain'}

    # Call _send_response
    job_id = "test-empty-job"
    service._send_response(job_id, mock_response)

    # Verify message was sent with CRC32 of empty data
    assert len(sent_messages) == 1
    response_msg = sent_messages[0]

    assert response_msg['job_id'] == job_id
    assert response_msg['status_code'] == 204
    assert response_msg['crc32'] == expected_crc32


def test_portal_unicode_json_response_crc32():
    """Test portal correctly calculates CRC32 for JSON with Unicode."""
    # Create portal service with mocked Kafka
    kafka_config = KafkaConfig()
    portal_config = PortalConfig(target_api_url="http://localhost:8080")
    service = PortalService(kafka_config, portal_config, oauth_config=None)

    # Mock the Kafka producer
    service._producer = MagicMock()
    sent_messages = []

    def capture_send(topic, key, value):
        sent_messages.append(value)

    service._producer.send.side_effect = capture_send
    service._producer.flush = MagicMock()

    # Mock JSON response with Unicode characters
    json_data = '{"message": "Hello 世界 🌍", "status": "成功"}'
    json_bytes = json_data.encode('utf-8')
    expected_crc32 = zlib.crc32(json_bytes) & 0xffffffff

    mock_response = Mock()
    mock_response.content = json_bytes
    mock_response.text = json_data
    mock_response.status_code = 200
    mock_response.headers = {'Content-Type': 'application/json; charset=utf-8'}

    # Call _send_response
    job_id = "test-unicode-job"
    service._send_response(job_id, mock_response)

    # Verify message was sent with correct CRC32
    assert len(sent_messages) == 1
    response_msg = sent_messages[0]

    assert response_msg['job_id'] == job_id
    assert response_msg['crc32'] == expected_crc32
    assert response_msg['is_json'] is True
