"""Tests for CRC32 checksum validation."""

import os
import tempfile
import zlib
import pytest
from kafkasend.common.models import KafkaRequestMessage, MessageType, HttpMethod
from kafkasend.portal.job_manager import JobManager, JobState


def test_crc32_calculation():
    """Test CRC32 calculation for a file."""
    # Create a temporary file
    with tempfile.NamedTemporaryFile(delete=False) as f:
        test_data = b"Hello, World! This is test data for CRC32 verification."
        f.write(test_data)
        temp_file = f.name

    try:
        # Calculate CRC32
        expected_crc32 = zlib.crc32(test_data) & 0xffffffff

        # Verify CRC32 calculation matches
        crc = 0
        with open(temp_file, 'rb') as f:
            while chunk := f.read(65536):
                crc = zlib.crc32(chunk, crc)
        actual_crc32 = crc & 0xffffffff

        assert actual_crc32 == expected_crc32

    finally:
        os.unlink(temp_file)


def test_job_state_crc32_verification_success():
    """Test successful CRC32 verification in JobState."""
    test_data = b"Test data for CRC32 verification"
    expected_crc32 = zlib.crc32(test_data) & 0xffffffff

    # Create a job state with expected CRC32
    job = JobState(
        job_id="test-job-123",
        method=HttpMethod.POST,
        endpoint="/api/upload",
        headers={},
        filename="test.bin",
        content_type="application/octet-stream",
        expected_crc32=expected_crc32,
        total_chunks=1
    )

    # Add the chunk
    job.add_chunk(0, test_data)

    # Get complete data should succeed with matching CRC32
    complete_data = job.get_complete_data()
    assert complete_data == test_data


def test_job_state_crc32_verification_failure():
    """Test CRC32 verification failure in JobState."""
    test_data = b"Test data for CRC32 verification"
    wrong_crc32 = 12345678  # Intentionally wrong CRC32

    # Create a job state with wrong CRC32
    job = JobState(
        job_id="test-job-456",
        method=HttpMethod.POST,
        endpoint="/api/upload",
        headers={},
        filename="test.bin",
        content_type="application/octet-stream",
        expected_crc32=wrong_crc32,
        total_chunks=1
    )

    # Add the chunk
    job.add_chunk(0, test_data)

    # Get complete data should raise ValueError due to CRC32 mismatch
    with pytest.raises(ValueError, match="CRC32 checksum mismatch"):
        job.get_complete_data()


def test_job_state_no_crc32_verification():
    """Test that no CRC32 verification happens when crc32 is None."""
    test_data = b"Test data without CRC32 verification"

    # Create a job state without CRC32
    job = JobState(
        job_id="test-job-789",
        method=HttpMethod.POST,
        endpoint="/api/upload",
        headers={},
        filename="test.bin",
        content_type="application/octet-stream",
        expected_crc32=None,  # No CRC32 verification
        total_chunks=1
    )

    # Add the chunk
    job.add_chunk(0, test_data)

    # Get complete data should succeed without verification
    complete_data = job.get_complete_data()
    assert complete_data == test_data


def test_job_manager_with_crc32():
    """Test JobManager integration with CRC32."""
    job_manager = JobManager()

    test_data = b"Integration test data"
    expected_crc32 = zlib.crc32(test_data) & 0xffffffff

    # Create START message with CRC32
    start_message = KafkaRequestMessage(
        job_id="integration-test-job",
        message_type=MessageType.START,
        sequence=0,
        total_chunks=1,
        method=HttpMethod.POST,
        endpoint="/api/upload",
        headers={},
        filename="test.bin",
        content_type="application/octet-stream",
        crc32=expected_crc32
    )

    # Start the job
    job = job_manager.start_job(start_message)
    assert job.expected_crc32 == expected_crc32

    # Add chunk with encoded data
    from kafkasend.common.chunking import encode_chunk
    chunk_message = KafkaRequestMessage(
        job_id="integration-test-job",
        message_type=MessageType.CHUNK,
        sequence=0,
        total_chunks=1,
        data=encode_chunk(test_data)
    )

    completed_job = job_manager.add_chunk(chunk_message)
    assert completed_job is not None

    # Verify CRC32 passes
    complete_data = completed_job.get_complete_data()
    assert complete_data == test_data


def test_job_manager_with_wrong_crc32():
    """Test JobManager detects CRC32 mismatch."""
    job_manager = JobManager()

    test_data = b"Integration test data with wrong CRC32"
    wrong_crc32 = 99999999

    # Create START message with wrong CRC32
    start_message = KafkaRequestMessage(
        job_id="integration-test-job-fail",
        message_type=MessageType.START,
        sequence=0,
        total_chunks=1,
        method=HttpMethod.POST,
        endpoint="/api/upload",
        headers={},
        filename="test.bin",
        content_type="application/octet-stream",
        crc32=wrong_crc32
    )

    # Start the job
    job = job_manager.start_job(start_message)

    # Add chunk with encoded data
    from kafkasend.common.chunking import encode_chunk
    chunk_message = KafkaRequestMessage(
        job_id="integration-test-job-fail",
        message_type=MessageType.CHUNK,
        sequence=0,
        total_chunks=1,
        data=encode_chunk(test_data)
    )

    completed_job = job_manager.add_chunk(chunk_message)
    assert completed_job is not None

    # Verify CRC32 check fails
    with pytest.raises(ValueError, match="CRC32 checksum mismatch"):
        completed_job.get_complete_data()


def test_multi_chunk_crc32_verification():
    """Test CRC32 verification with multiple chunks."""
    job_manager = JobManager()

    # Create test data split into multiple chunks
    chunk1 = b"First chunk of data. "
    chunk2 = b"Second chunk of data. "
    chunk3 = b"Third and final chunk."
    complete_data = chunk1 + chunk2 + chunk3
    expected_crc32 = zlib.crc32(complete_data) & 0xffffffff

    # Create START message with CRC32
    start_message = KafkaRequestMessage(
        job_id="multi-chunk-job",
        message_type=MessageType.START,
        sequence=0,
        total_chunks=3,
        method=HttpMethod.POST,
        endpoint="/api/upload",
        headers={},
        filename="test.bin",
        content_type="application/octet-stream",
        crc32=expected_crc32
    )

    # Start the job
    job_manager.start_job(start_message)

    # Add chunks
    from kafkasend.common.chunking import encode_chunk

    # Add chunk 0
    chunk_message = KafkaRequestMessage(
        job_id="multi-chunk-job",
        message_type=MessageType.CHUNK,
        sequence=0,
        total_chunks=3,
        data=encode_chunk(chunk1)
    )
    result = job_manager.add_chunk(chunk_message)
    assert result is None  # Not complete yet

    # Add chunk 1
    chunk_message = KafkaRequestMessage(
        job_id="multi-chunk-job",
        message_type=MessageType.CHUNK,
        sequence=1,
        total_chunks=3,
        data=encode_chunk(chunk2)
    )
    result = job_manager.add_chunk(chunk_message)
    assert result is None  # Not complete yet

    # Add chunk 2
    chunk_message = KafkaRequestMessage(
        job_id="multi-chunk-job",
        message_type=MessageType.CHUNK,
        sequence=2,
        total_chunks=3,
        data=encode_chunk(chunk3)
    )
    completed_job = job_manager.add_chunk(chunk_message)
    assert completed_job is not None  # Complete now

    # Verify CRC32 passes for reassembled data
    reassembled_data = completed_job.get_complete_data()
    assert reassembled_data == complete_data


# ============================================================================
# Response CRC32 Tests
# ============================================================================


def test_response_state_crc32_verification_json():
    """Test CRC32 verification for JSON response."""
    from kafkasend.client.receiver import ResponseState
    from kafkasend.common.models import KafkaResponseMessage, MessageType

    json_data = '{"message": "success", "id": 123}'
    expected_crc32 = zlib.crc32(json_data.encode('utf-8')) & 0xffffffff

    # Create response state
    state = ResponseState("test-response-job")

    # Simulate receiving a response message
    response_msg = KafkaResponseMessage(
        job_id="test-response-job",
        message_type=MessageType.START,
        sequence=0,
        total_chunks=1,
        status_code=200,
        headers={"Content-Type": "application/json"},
        data=json_data,
        is_json=True,
        crc32=expected_crc32
    )

    # Manually update state (simulating _process_response)
    state.status_code = response_msg.status_code
    state.headers = response_msg.headers
    state.total_chunks = response_msg.total_chunks
    state.expected_crc32 = response_msg.crc32
    state.is_json = response_msg.is_json
    state.add_chunk(response_msg.sequence, response_msg.data)

    # Verify CRC32 passes
    complete_data = state.get_complete_data()
    assert complete_data == json_data


def test_response_state_crc32_verification_binary():
    """Test CRC32 verification for binary response."""
    from kafkasend.client.receiver import ResponseState
    from kafkasend.common.models import KafkaResponseMessage, MessageType
    from kafkasend.common.chunking import encode_chunk

    binary_data = b"Binary file content with special chars \x00\x01\x02"
    expected_crc32 = zlib.crc32(binary_data) & 0xffffffff
    encoded_data = encode_chunk(binary_data)

    # Create response state
    state = ResponseState("test-binary-response-job")

    # Simulate receiving a binary response message
    response_msg = KafkaResponseMessage(
        job_id="test-binary-response-job",
        message_type=MessageType.START,
        sequence=0,
        total_chunks=1,
        status_code=200,
        headers={"Content-Type": "application/octet-stream"},
        data=encoded_data,
        is_json=False,
        crc32=expected_crc32
    )

    # Manually update state
    state.status_code = response_msg.status_code
    state.headers = response_msg.headers
    state.total_chunks = response_msg.total_chunks
    state.expected_crc32 = response_msg.crc32
    state.is_json = response_msg.is_json
    state.add_chunk(response_msg.sequence, response_msg.data)

    # Verify CRC32 passes
    complete_data = state.get_complete_data()
    assert complete_data == encoded_data


def test_response_state_crc32_verification_failure():
    """Test CRC32 verification failure for response."""
    from kafkasend.client.receiver import ResponseState
    from kafkasend.common.models import KafkaResponseMessage, MessageType

    json_data = '{"message": "test data"}'
    wrong_crc32 = 99999999

    # Create response state
    state = ResponseState("test-fail-response-job")

    # Simulate receiving response with wrong CRC32
    response_msg = KafkaResponseMessage(
        job_id="test-fail-response-job",
        message_type=MessageType.START,
        sequence=0,
        total_chunks=1,
        status_code=200,
        headers={"Content-Type": "application/json"},
        data=json_data,
        is_json=True,
        crc32=wrong_crc32
    )

    # Manually update state
    state.status_code = response_msg.status_code
    state.total_chunks = response_msg.total_chunks
    state.expected_crc32 = response_msg.crc32
    state.is_json = response_msg.is_json
    state.add_chunk(response_msg.sequence, response_msg.data)

    # Verify CRC32 check fails
    with pytest.raises(ValueError, match="CRC32 checksum mismatch"):
        state.get_complete_data()


def test_response_state_no_crc32():
    """Test response without CRC32 verification (backwards compatible)."""
    from kafkasend.client.receiver import ResponseState
    from kafkasend.common.models import KafkaResponseMessage, MessageType

    json_data = '{"status": "ok"}'

    # Create response state
    state = ResponseState("test-no-crc32-response")

    # Simulate receiving response without CRC32
    response_msg = KafkaResponseMessage(
        job_id="test-no-crc32-response",
        message_type=MessageType.START,
        sequence=0,
        total_chunks=1,
        status_code=200,
        data=json_data,
        is_json=True,
        crc32=None  # No CRC32
    )

    # Manually update state
    state.total_chunks = response_msg.total_chunks
    state.is_json = response_msg.is_json
    state.add_chunk(response_msg.sequence, response_msg.data)

    # Should work without CRC32 verification
    complete_data = state.get_complete_data()
    assert complete_data == json_data


def test_response_multi_chunk_crc32():
    """Test CRC32 verification for multi-chunk response."""
    from kafkasend.client.receiver import ResponseState
    from kafkasend.common.models import KafkaResponseMessage, MessageType

    # Simulate a large JSON response split into chunks
    chunk1 = '{"data": ["item1", '
    chunk2 = '"item2", "item3", '
    chunk3 = '"item4"]}'
    complete_json = chunk1 + chunk2 + chunk3
    expected_crc32 = zlib.crc32(complete_json.encode('utf-8')) & 0xffffffff

    # Create response state
    state = ResponseState("test-multi-chunk-response")

    # First message with CRC32
    response_msg1 = KafkaResponseMessage(
        job_id="test-multi-chunk-response",
        message_type=MessageType.CHUNK,
        sequence=0,
        total_chunks=3,
        status_code=200,
        headers={"Content-Type": "application/json"},
        data=chunk1,
        is_json=True,
        crc32=expected_crc32
    )

    # Update state from first message
    state.status_code = response_msg1.status_code
    state.headers = response_msg1.headers
    state.total_chunks = response_msg1.total_chunks
    state.expected_crc32 = response_msg1.crc32
    state.is_json = response_msg1.is_json
    state.add_chunk(response_msg1.sequence, response_msg1.data)

    # Second chunk
    response_msg2 = KafkaResponseMessage(
        job_id="test-multi-chunk-response",
        message_type=MessageType.CHUNK,
        sequence=1,
        total_chunks=3,
        data=chunk2,
        is_json=True
    )
    state.add_chunk(response_msg2.sequence, response_msg2.data)

    # Third chunk
    response_msg3 = KafkaResponseMessage(
        job_id="test-multi-chunk-response",
        message_type=MessageType.CHUNK,
        sequence=2,
        total_chunks=3,
        data=chunk3,
        is_json=True
    )
    state.add_chunk(response_msg3.sequence, response_msg3.data)

    # Verify CRC32 passes for complete response
    assert state.is_complete()
    complete_data = state.get_complete_data()
    assert complete_data == complete_json
