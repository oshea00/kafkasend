# KafkaSend Protocol Specification

This document describes the message protocol used by KafkaSend to transmit files and HTTP requests through Kafka topics.

## Overview

KafkaSend uses a chunked message protocol to enable large file transfers (up to 50MB+) through Kafka, which has message size limitations. The protocol supports:

- Multi-chunk file transfers with sequence ordering
- Job-based request/response correlation
- Multiple HTTP methods (GET, POST, PUT, PATCH, DELETE)
- Custom headers and multipart file uploads
- Error handling and status reporting

## Architecture

```mermaid
graph LR
    A[Client CLI] -->|api-requests<br/>Kafka Topic| B[Portal Service<br/>Bridge]
    B -->|api-responses<br/>Kafka Topic| A
    B -->|HTTP/REST<br/>with OAuth2| C[REST API<br/>Server]
    C -->|HTTP Response<br/>JSON/Binary| B

    style A fill:#e1f5ff,stroke:#01579b,stroke-width:2px
    style B fill:#fff3e0,stroke:#e65100,stroke-width:2px
    style C fill:#f3e5f5,stroke:#4a148c,stroke-width:2px
```

## Message Types

The protocol defines four message types:

| Type | Purpose |
|------|---------|
| `START` | Initiates a new job with metadata and configuration |
| `CHUNK` | Carries a chunk of binary data (base64 encoded) |
| `END` | Optional completion marker for requests with no data |
| `ERROR` | Reports errors during processing |

## Bidirectional Chunking

The KafkaSend protocol implements **bidirectional chunking** to handle large data in both directions:

### Request Direction: Client → Portal

**Client responsibilities:**
- Calculate chunk count based on file size
- Split large files into 650KB chunks
- Base64 encode each chunk
- Send START message followed by CHUNK messages
- Include sequence numbers and total chunk count

**Portal responsibilities:**
- Receive and accumulate chunks in memory
- Track sequence numbers to ensure all chunks received
- Reassemble chunks in correct order
- Decode base64 back to binary
- Forward complete data to REST API

### Response Direction: Portal → Client

**Portal responsibilities:**
- Receive HTTP response from REST API
- Check response size (> 650KB requires chunking)
- Base64 encode binary responses
- Split large responses into 650KB chunks
- Send CHUNK messages with sequence numbers
- Include status code and headers in first message

**Client responsibilities:**
- Receive and accumulate response chunks
- Track sequence numbers to ensure all chunks received
- Reassemble chunks in correct order
- Decode base64 back to binary/text
- Display or save the complete response

### Key Characteristics

| Aspect | Request Chunking | Response Chunking |
|--------|------------------|-------------------|
| **Who chunks?** | Client | Portal |
| **Who reassembles?** | Portal | Client |
| **Chunk size** | 650KB (before base64) | 650KB (before base64) |
| **When needed?** | Files > 650KB | Responses > 650KB |
| **Encoding** | Base64 | Base64 |
| **Message types** | START + CHUNKs | START/CHUNKs |

```mermaid
graph TD
    subgraph "Request Flow - Client Chunks"
        A1[Large File<br/>2MB] --> A2[Client: Split into 4 chunks]
        A2 --> A3[Client: Base64 encode]
        A3 --> A4[Send to Kafka]
        A4 --> A5[Portal: Accumulate]
        A5 --> A6[Portal: Reassemble]
        A6 --> A7[Portal: Decode base64]
        A7 --> A8[Send to REST API]
    end

    subgraph "Response Flow - Portal Chunks"
        B1[REST API Response<br/>5MB] --> B2[Portal: Base64 encode]
        B2 --> B3[Portal: Split into 8 chunks]
        B3 --> B4[Send to Kafka]
        B4 --> B5[Client: Accumulate]
        B5 --> B6[Client: Reassemble]
        B6 --> B7[Client: Decode base64]
        B7 --> B8[Display/Save]
    end

    A8 -.->|HTTP Request| B1

    style A2 fill:#e1f5ff,stroke:#01579b
    style A5 fill:#fff3e0,stroke:#e65100
    style B3 fill:#fff3e0,stroke:#e65100
    style B5 fill:#e1f5ff,stroke:#01579b
```

## Protocol Flow

### Single-Chunk Upload (Small File)

```mermaid
sequenceDiagram
    participant C as Client CLI
    participant KR as Kafka<br/>(api-requests)
    participant P as Portal Service
    participant KS as Kafka<br/>(api-responses)
    participant A as REST API

    C->>C: Read file (< 650KB)
    C->>C: Encode as base64
    C->>KR: START message<br/>(total_chunks=1, data)
    KR->>P: Consume message
    P->>P: Job started<br/>All chunks received
    P->>P: Decode base64
    P->>A: HTTP POST (multipart)
    A-->>P: HTTP 200 Response
    P->>P: Encode response
    P->>KS: Response message<br/>(status=200, data)
    KS->>C: Consume response
    C->>C: Display result
```

### Multi-Chunk Upload (Large File)

```mermaid
sequenceDiagram
    participant C as Client CLI
    participant KR as Kafka<br/>(api-requests)
    participant P as Portal Service
    participant A as REST API

    C->>C: Calculate chunks<br/>(file_size / 650KB)
    C->>KR: START message<br/>(total_chunks=4)
    C->>KR: CHUNK message<br/>(seq=0, data)
    C->>KR: CHUNK message<br/>(seq=1, data)
    C->>KR: CHUNK message<br/>(seq=2, data)
    C->>KR: CHUNK message<br/>(seq=3, data)

    Note over P: Accumulating chunks...
    KR->>P: Consume messages
    P->>P: Job started
    P->>P: Chunk 0 received
    P->>P: Chunk 1 received
    P->>P: Chunk 2 received
    P->>P: Chunk 3 received
    P->>P: All chunks complete!

    P->>P: Reassemble chunks
    P->>P: Decode base64
    P->>A: HTTP POST<br/>(multipart, 2MB file)
    A-->>P: HTTP 200 Response
    P->>P: Check response size
    P->>Kafka: Response message<br/>(single or chunked)
```

### Simple Request (No Body)

```mermaid
sequenceDiagram
    participant C as Client CLI
    participant KR as Kafka<br/>(api-requests)
    participant P as Portal Service
    participant A as REST API

    C->>KR: START message<br/>(method=GET, total_chunks=0)
    KR->>P: Consume message
    P->>P: Job started<br/>No data expected
    P->>A: HTTP GET request
    A-->>P: HTTP 200 JSON Response
    P->>Kafka: Response message<br/>(is_json=true)
```

### Large Response Handling (Chunked by Portal)

When the REST API returns a large response (> 650KB), the portal automatically chunks it:

```mermaid
sequenceDiagram
    participant C as Client CLI
    participant KR as Kafka<br/>(api-requests)
    participant P as Portal Service
    participant KS as Kafka<br/>(api-responses)
    participant A as REST API

    C->>KR: START message<br/>(file upload)
    KR->>P: Process request
    P->>A: HTTP POST
    A-->>P: HTTP 200<br/>(Large response: 5MB)

    Note over P: Response > 650KB<br/>Chunking required!

    P->>P: Calculate chunks<br/>(5MB / 650KB = 8)
    P->>P: Encode as base64
    P->>KS: CHUNK message<br/>(seq=0, total=8)
    P->>KS: CHUNK message<br/>(seq=1, total=8)
    P->>KS: CHUNK message<br/>(seq=2, total=8)
    P->>KS: ...
    P->>KS: CHUNK message<br/>(seq=7, total=8)

    Note over C: Accumulating response chunks...
    KS->>C: Consume messages
    C->>C: Chunk 0 received
    C->>C: Chunk 1 received
    C->>C: Chunk 2 received
    C->>C: ...chunks 3-6...
    C->>C: Chunk 7 received
    C->>C: All chunks complete!

    C->>C: Reassemble chunks
    C->>C: Decode base64
    C->>C: Save to file or display
```

**Key Points:**
- **Portal responsibility**: Chunk large responses (> 650KB) before sending to Kafka
- **Client responsibility**: Reassemble response chunks in correct order
- **Same chunking logic**: Both request and response use 650KB chunks
- **Base64 encoding**: Applied to binary responses before chunking

### Error Handling

```mermaid
sequenceDiagram
    participant C as Client CLI
    participant KR as Kafka<br/>(api-requests)
    participant P as Portal Service
    participant A as REST API

    C->>KR: START message
    C->>KR: CHUNK message (seq=0)
    KR->>P: Consume messages
    P->>P: Job started
    P->>P: Error: Invalid data
    P->>Kafka: ERROR message<br/>(error_message)
    P->>P: Job cancelled
```

## Message Formats

### Request Message Schema

All request messages sent to the `api-requests` topic follow this schema:

```json
{
  "job_id": "uuid-v4",
  "message_type": "START|CHUNK|END|ERROR",
  "sequence": 0,
  "total_chunks": 4,

  // HTTP Request Details (START message only)
  "method": "POST|GET|PUT|PATCH|DELETE",
  "endpoint": "/api/upload",
  "headers": {
    "Authorization": "Bearer token",
    "X-Custom-Header": "value"
  },

  // File Details (START message only)
  "filename": "document.pdf",
  "content_type": "application/pdf",

  // Data (START and CHUNK messages)
  "data": "base64-encoded-binary-data",

  // Error Details (ERROR message only)
  "error_message": "Error description"
}
```

### Response Message Schema

All response messages sent to the `api-responses` topic follow this schema:

```json
{
  "job_id": "uuid-v4",
  "message_type": "START|CHUNK|ERROR",
  "sequence": 0,
  "total_chunks": 1,

  // HTTP Response Details
  "status_code": 200,
  "headers": {
    "Content-Type": "application/json",
    "Content-Length": "1234"
  },

  // Response Data
  "data": "base64-or-plain-text",
  "is_json": true,

  // Error Details (ERROR message only)
  "error_message": "Error description"
}
```

## Detailed Message Types

### START Message (Request)

Initiates a new job and provides all metadata needed for the HTTP request.

**Required Fields:**
- `job_id` - Unique identifier (UUID v4)
- `message_type` = `"START"`
- `sequence` = `0`
- `total_chunks` - Number of chunks to expect (0 if no body)
- `method` - HTTP method
- `endpoint` - Target API path

**Optional Fields:**
- `headers` - HTTP headers (auth, content-type, etc.)
- `filename` - Original filename for multipart uploads
- `content_type` - MIME type of the file
- `data` - Base64 encoded data (if `total_chunks` = 1)

**Example - Small File Upload:**
```json
{
  "job_id": "a7cf937b-b8ca-41e5-a9d1-e380bc726dea",
  "message_type": "START",
  "sequence": 0,
  "total_chunks": 1,
  "method": "POST",
  "endpoint": "/api/upload",
  "headers": {},
  "filename": "test.txt",
  "content_type": "text/plain",
  "data": "VGhpcyBpcyBhIHRlc3QgZmlsZSBmb3IgZGVtb25zdHJhdGlvbiBwdXJwb3Nlcy4K"
}
```

**Example - Large File Upload (Start):**
```json
{
  "job_id": "c51e5e4f-bba9-470e-956e-ba190bac31ad",
  "message_type": "START",
  "sequence": 0,
  "total_chunks": 4,
  "method": "POST",
  "endpoint": "/api/upload",
  "headers": {},
  "filename": "large-file.bin",
  "content_type": "application/octet-stream"
}
```

**Example - GET Request (No Body):**
```json
{
  "job_id": "def456...",
  "message_type": "START",
  "sequence": 0,
  "total_chunks": 0,
  "method": "GET",
  "endpoint": "/api/status",
  "headers": {
    "Authorization": "Bearer eyJhbGc..."
  }
}
```

### CHUNK Message (Request)

Carries a chunk of binary data, base64 encoded.

**Required Fields:**
- `job_id` - Matches the START message
- `message_type` = `"CHUNK"`
- `sequence` - Chunk sequence number (0-indexed)
- `total_chunks` - Same as START message
- `data` - Base64 encoded binary chunk

**Optional Fields:**
- None

**Example:**
```json
{
  "job_id": "c51e5e4f-bba9-470e-956e-ba190bac31ad",
  "message_type": "CHUNK",
  "sequence": 1,
  "total_chunks": 4,
  "data": "iVBORw0KGgoAAAANSUhEUgAA..."
}
```

**Chunk Size Calculation:**
- Maximum chunk size: **650 KB** (before encoding)
- After base64 encoding: ~866 KB
- Plus JSON overhead: ~870 KB total message size
- Well under Kafka's 1 MB default limit

### END Message (Request)

Optional marker to signal completion of a request that has no data chunks.

**Required Fields:**
- `job_id` - Matches the START message
- `message_type` = `"END"`

**Example:**
```json
{
  "job_id": "def456...",
  "message_type": "END"
}
```

### Response Messages

The portal sends response messages back on the `api-responses` topic.

**Example - Success Response:**
```json
{
  "job_id": "a7cf937b-b8ca-41e5-a9d1-e380bc726dea",
  "message_type": "START",
  "sequence": 0,
  "total_chunks": 1,
  "status_code": 200,
  "headers": {
    "Content-Type": "application/json",
    "Content-Length": "361"
  },
  "data": "{\"message\":\"File uploaded successfully\",\"filename\":\"test.txt\",\"size\":48}",
  "is_json": true
}
```

**Example - Error Response:**
```json
{
  "job_id": "abc123...",
  "message_type": "ERROR",
  "error_message": "'str' object has no attribute 'value'"
}
```

## Job State Machine

```mermaid
stateDiagram-v2
    [*] --> Started: START message
    Started --> Accumulating: CHUNK messages
    Accumulating --> Accumulating: More CHUNKs
    Accumulating --> Complete: All chunks received
    Complete --> Executing: Decode & reassemble
    Executing --> Responding: HTTP request sent
    Responding --> [*]: Response sent

    Started --> Error: Invalid message
    Accumulating --> Error: Missing chunk
    Executing --> Error: HTTP error
    Error --> [*]: Error response sent
```

## Portal Processing Logic

### Job Initialization

1. Receive START message
2. Validate required fields (method, endpoint)
3. Create job state with metadata
4. If `total_chunks` = 0: execute immediately
5. If `total_chunks` > 0: wait for chunks

### Chunk Accumulation

1. Receive CHUNK messages
2. Validate job exists
3. Store chunk at sequence index
4. Check if all chunks received
5. When complete: proceed to execution

### Request Execution

1. Decode all base64 chunks
2. Reassemble into complete binary data
3. Build HTTP request:
   - If `filename` present: multipart/form-data upload
   - Otherwise: raw body data
4. Add OAuth2 token (if configured)
5. Send HTTP request to target API
6. Wait for response (with timeout)

### Response Handling

**Portal responsibilities (chunking large responses):**

1. Receive HTTP response from REST API
2. Check content type (JSON vs binary)
3. For binary responses: encode as base64
4. **Calculate response size:**
   - If ≤ 650KB: send single response message
   - If > 650KB: **chunk the response**
5. For chunked responses:
   - Split response into 650KB chunks
   - Send first CHUNK with status_code and headers
   - Send subsequent CHUNKs with sequence numbers
   - Include total_chunks in all messages
6. Flush all messages to `api-responses` topic
7. Complete job and cleanup

**Client responsibilities (reassembling responses):**

1. Listen on `api-responses` topic for matching job_id
2. Accumulate CHUNK messages by sequence number
3. Track progress (chunks_received / total_chunks)
4. When all chunks received:
   - Sort chunks by sequence number
   - Concatenate chunk data
   - Decode base64 (if binary)
   - Parse JSON (if is_json=true)
5. Display or save complete response
6. Close consumer connection

## Error Conditions

| Error | Cause | Recovery |
|-------|-------|----------|
| `MessageSizeTooLargeError` | Chunk exceeds 1MB after encoding | Reduce `MAX_CHUNK_SIZE` |
| `JobNotFound` | CHUNK received before START | Client should retry |
| `MissingChunks` | Not all chunks received | Timeout, send ERROR response |
| `InvalidData` | Base64 decode fails | Send ERROR response |
| `HTTPError` | Target API returns error | Return error status to client |
| `Timeout` | Request takes too long | Send ERROR response |
| `MaxJobsExceeded` | Too many concurrent jobs | Client should retry later |

## Configuration

### Kafka Topics

- **Request Topic**: `api-requests` (configurable via `KAFKA_REQUEST_TOPIC`)
- **Response Topic**: `api-responses` (configurable via `KAFKA_RESPONSE_TOPIC`)

### Size Limits

- **Max Chunk Size**: 650 KB (before base64 encoding)
- **Max File Size**: Unlimited (chunked automatically)
- **Kafka Message Limit**: 1 MB (default)
- **Max Request Size**: Configurable on producer (`max_request_size`)

### Timeouts

- **Job Timeout**: 300 seconds (configurable via `PORTAL_JOB_TIMEOUT_SECONDS`)
- **Kafka Session**: 30 seconds (configurable via `KAFKA_SESSION_TIMEOUT_MS`)

## Best Practices

### For Clients

1. **Generate unique job IDs** using UUID v4
2. **Calculate chunks correctly** using `calculate_chunk_count()`
3. **Send START message first** before any CHUNKs
4. **Sequence chunks properly** starting from 0
5. **Handle timeouts gracefully** and retry if needed

### For Portal

1. **Validate all incoming messages** before processing
2. **Track job state carefully** to detect missing chunks
3. **Clean up completed jobs** to prevent memory leaks
4. **Log all operations** for debugging
5. **Handle OAuth token refresh** proactively

### For API Servers

1. **Support multipart/form-data** for file uploads
2. **Return JSON responses** when possible (easier to handle)
3. **Include proper status codes** (200, 400, 500, etc.)
4. **Handle large files efficiently** (streaming, etc.)
5. **Implement authentication** (Bearer tokens, etc.)

## Security Considerations

- **Job IDs are UUIDs**: Hard to guess, provides some isolation
- **OAuth2 tokens**: Securely managed and auto-refreshed
- **No data persistence**: Chunks stored in memory only
- **Kafka ACLs**: Should be configured for production
- **TLS/SSL**: Enable for production Kafka and HTTP traffic

## Performance Characteristics

### Throughput

- **Small files (< 650KB)**: Single message, low latency
- **Large files (2-50MB)**: Multiple chunks, higher latency
- **Chunk processing**: ~100ms per chunk
- **HTTP request**: Depends on target API

### Scalability

- **Concurrent jobs**: Limited by `PORTAL_MAX_CONCURRENT_JOBS` (default: 10)
- **Kafka partitions**: Can parallelize across multiple portal instances
- **Consumer groups**: Each portal joins same group for load balancing

## Limitations

- **Consumer offset timing**: Response waiting may fail due to consumer group coordination
- **In-memory storage**: Large files consume portal memory
- **No persistence**: Failed jobs are lost
- **Synchronous processing**: One job at a time per portal instance

## Future Enhancements

- **Async response handling**: Decouple request and response processing
- **Persistent storage**: Store chunks in Redis/S3 for large files
- **Retry logic**: Automatic retry on transient failures
- **Compression**: Compress chunks before base64 encoding
- **Streaming**: Stream large responses back without accumulation
