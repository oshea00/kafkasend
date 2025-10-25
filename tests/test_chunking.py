"""Tests for chunking utilities."""

import os
import tempfile
from kafkasend.common.chunking import (
    chunk_file,
    encode_chunk,
    decode_chunk,
    reassemble_chunks,
    calculate_chunk_count,
)


def test_encode_decode_chunk():
    """Test encoding and decoding of chunks."""
    original_data = b"Hello, World! This is test data."
    encoded = encode_chunk(original_data)
    decoded = decode_chunk(encoded)
    assert decoded == original_data


def test_chunk_file():
    """Test file chunking."""
    # Create a temporary file
    with tempfile.NamedTemporaryFile(delete=False) as f:
        test_data = b"A" * 10000  # 10KB of data
        f.write(test_data)
        temp_file = f.name

    try:
        # Chunk with small size
        chunk_size = 1000
        chunks = list(chunk_file(temp_file, chunk_size=chunk_size))

        # Should have 10 chunks
        assert len(chunks) == 10

        # Reassemble should match original
        reassembled = reassemble_chunks(chunks)
        assert reassembled == test_data

    finally:
        os.unlink(temp_file)


def test_calculate_chunk_count():
    """Test chunk count calculation."""
    with tempfile.NamedTemporaryFile(delete=False) as f:
        test_data = b"B" * 5500  # 5.5KB
        f.write(test_data)
        temp_file = f.name

    try:
        chunk_count = calculate_chunk_count(temp_file, chunk_size=1000)
        # Should need 6 chunks for 5500 bytes with 1000 byte chunks
        assert chunk_count == 6

    finally:
        os.unlink(temp_file)


def test_reassemble_empty():
    """Test reassembling empty chunk list."""
    result = reassemble_chunks([])
    assert result == b""


def test_reassemble_single():
    """Test reassembling single chunk."""
    chunk = b"Single chunk"
    result = reassemble_chunks([chunk])
    assert result == chunk
