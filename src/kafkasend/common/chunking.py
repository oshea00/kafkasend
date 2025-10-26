"""Utilities for chunking and reassembling large files."""

import base64
from typing import Iterator, List


# Kafka message size limit calculation
# Kafka default max message size is 1MB (1,048,576 bytes)
# Base64 encoding increases size by ~33% (4 bytes for every 3 bytes)
# JSON message wrapper adds additional overhead (~200-500 bytes)
#
# Calculation:
# - Target final message size: 950KB (safety margin)
# - Less JSON overhead: ~945KB for base64 data
# - Divide by 1.333 (base64 expansion): ~709KB
# - Use 650KB for safety: 650KB * 1.33 = ~866KB base64, ~870KB total
MAX_CHUNK_SIZE = 650 * 1024  # 650 KB (before base64 encoding)


def chunk_file(file_path: str, chunk_size: int = MAX_CHUNK_SIZE) -> Iterator[bytes]:
    """
    Read a file and yield chunks of specified size.

    Args:
        file_path: Path to the file to chunk
        chunk_size: Maximum size of each chunk in bytes

    Yields:
        Chunks of binary data
    """
    with open(file_path, 'rb') as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            yield chunk


def encode_chunk(data: bytes) -> str:
    """
    Encode binary data as base64 string.

    Args:
        data: Binary data to encode

    Returns:
        Base64 encoded string
    """
    return base64.b64encode(data).decode('utf-8')


def decode_chunk(data: str) -> bytes:
    """
    Decode base64 string to binary data.

    Args:
        data: Base64 encoded string

    Returns:
        Binary data
    """
    return base64.b64decode(data.encode('utf-8'))


def reassemble_chunks(chunks: List[bytes]) -> bytes:
    """
    Reassemble a list of chunks into complete data.

    Args:
        chunks: List of binary chunks in order

    Returns:
        Complete binary data
    """
    return b''.join(chunks)


def calculate_chunk_count(file_path: str, chunk_size: int = MAX_CHUNK_SIZE) -> int:
    """
    Calculate how many chunks a file will be split into.

    Args:
        file_path: Path to the file
        chunk_size: Maximum size of each chunk

    Returns:
        Number of chunks required
    """
    import os
    file_size = os.path.getsize(file_path)
    return (file_size + chunk_size - 1) // chunk_size
