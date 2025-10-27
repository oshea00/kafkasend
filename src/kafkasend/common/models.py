"""Data models for Kafka messages and REST requests."""

from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field


class HttpMethod(str, Enum):
    """Supported HTTP methods."""

    GET = "GET"
    POST = "POST"
    PUT = "PUT"
    PATCH = "PATCH"
    DELETE = "DELETE"


class MessageType(str, Enum):
    """Types of messages in the protocol."""

    START = "START"  # First message of a request
    CHUNK = "CHUNK"  # Data chunk
    END = "END"      # Last message/completion marker
    ERROR = "ERROR"  # Error notification


class KafkaRequestMessage(BaseModel):
    """Message format for requests sent to Kafka."""

    job_id: str = Field(..., description="Unique identifier for this job")
    message_type: MessageType = Field(..., description="Type of message")
    sequence: int = Field(0, description="Sequence number for ordering chunks")
    total_chunks: Optional[int] = Field(None, description="Total number of chunks expected")

    # HTTP request details (in START message)
    method: Optional[HttpMethod] = Field(None, description="HTTP method")
    endpoint: Optional[str] = Field(None, description="Target API endpoint")
    headers: Optional[Dict[str, str]] = Field(None, description="HTTP headers")

    # File/data details
    filename: Optional[str] = Field(None, description="Original filename")
    content_type: Optional[str] = Field(None, description="Content type of the file")
    crc32: Optional[int] = Field(None, description="CRC32 checksum of complete data for integrity verification")

    # Chunk data (base64 encoded)
    data: Optional[str] = Field(None, description="Base64 encoded chunk data")

    # Error details
    error_message: Optional[str] = Field(None, description="Error description")

    model_config = ConfigDict(use_enum_values=True)


class KafkaResponseMessage(BaseModel):
    """Message format for responses sent back via Kafka."""

    job_id: str = Field(..., description="Job identifier matching the request")
    message_type: MessageType = Field(..., description="Type of message")
    sequence: int = Field(0, description="Sequence number for ordering")
    total_chunks: Optional[int] = Field(None, description="Total chunks in response")

    # Response details
    status_code: Optional[int] = Field(None, description="HTTP status code")
    headers: Optional[Dict[str, str]] = Field(None, description="Response headers")

    # Response data (base64 encoded for binary, or plain text for JSON)
    data: Optional[str] = Field(None, description="Response data")
    is_json: bool = Field(False, description="Whether data is JSON")

    # Error details
    error_message: Optional[str] = Field(None, description="Error description")

    model_config = ConfigDict(use_enum_values=True)
