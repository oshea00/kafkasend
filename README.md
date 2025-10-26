# KafkaSend

A Kafka-to-REST API bridge that enables sending large files (up to 50MB+) and HTTP requests through Kafka topics with automatic chunking, OAuth2 authentication support, and response streaming.

## Overview

KafkaSend consists of two main components:

1. **Portal Service**: A bridge service that listens on Kafka topics for requests, accumulates chunked messages, makes REST API calls (with OAuth2 JWT authentication), and streams responses back via Kafka.

2. **Client CLI**: A command-line tool that sends files and HTTP requests to the portal via Kafka, automatically chunking large files and reassembling responses.

## Features

- **Large File Support**: Handles files up to 50MB+ by automatically chunking them into Kafka-compatible message sizes (650KB chunks, accounting for base64 encoding overhead)
- **OAuth2 Machine-to-Machine**: Built-in support for JWT authentication with configurable OAuth2 providers
- **Full HTTP Verb Support**: Supports GET, POST, PUT, PATCH, DELETE with custom headers
- **Multipart Uploads**: Automatic handling of multipart/form-data for file uploads
- **Job-based Tracking**: Each request gets a unique job ID for tracking and response correlation
- **Concurrent Processing**: Portal service can handle multiple jobs simultaneously
- **Docker Ready**: Complete Docker Compose orchestration for easy deployment
- **Structured Logging**: Comprehensive logging with structlog for debugging and monitoring

## Architecture

```
Client CLI --> Kafka (requests) --> Portal Service --> REST API
           <-- Kafka (responses) <--
```

## Quick Start with Docker

### Prerequisites

- Docker and Docker Compose
- 4GB+ RAM available for Docker

### 1. Start the services

```bash
# Start Kafka, Portal, and Mock API
docker-compose up -d

# Wait for services to be healthy (30-60 seconds)
docker-compose ps
```

### 2. Send a test file

```bash
# Create a test file
echo "Hello from KafkaSend!" > testdata/hello.txt

# Send file using Docker client (use --no-wait to avoid hanging)
docker-compose run --rm client send-file \
  /testdata/hello.txt \
  --endpoint /api/upload \
  --method POST \
  --no-wait

# Check the uploaded file was saved
ls -lh uploads/
cat uploads/hello.txt

# View portal logs to confirm processing
docker-compose logs portal --tail=20
```

### 3. Verify the upload worked

The file should appear in `uploads/` directory within a few seconds. You can verify:

```bash
# Compare original and uploaded file
diff testdata/hello.txt uploads/hello.txt

# Check portal logs to see processing
docker-compose logs portal | grep "Request completed"

# Check mock API logs
docker-compose logs mock-api | grep "File received"
```

**Note**: The `--no-wait` flag is used because waiting for responses has a consumer offset timing issue in the current setup. The portal processes requests successfully (check logs to verify), but the client may not receive the response due to Kafka consumer group coordination. This is a known limitation in the Docker setup and doesn't affect the core functionality.

### 4. Stop services

```bash
docker-compose down
```

## Local Development Setup

### Installation

```bash
# Create virtual environment
python -m venv .venv
source .venv/bin/activate

# Install package
pip install -e ".[dev]"
```

### Configuration

```bash
# Copy environment example
cp .env.example .env

# Edit .env with your settings
```

### Running Services

```bash
# Start Kafka with Docker
docker-compose up -d zookeeper kafka

# Run portal
kafkasend-portal

# Use client
kafkasend-client send-file /path/to/file.pdf --endpoint /api/upload
```

## Configuration

### Kafka Configuration

- `KAFKA_BOOTSTRAP_SERVERS`: Kafka broker addresses (default: localhost:9092)
- `KAFKA_REQUEST_TOPIC`: Topic for requests (default: api-requests)
- `KAFKA_RESPONSE_TOPIC`: Topic for responses (default: api-responses)
- `KAFKA_CONSUMER_GROUP`: Consumer group ID (default: kafkasend-portal)
- `KAFKA_SESSION_TIMEOUT_MS`: Consumer session timeout in ms (default: 300000 = 5 minutes)
- `KAFKA_MAX_POLL_INTERVAL_MS`: Max time between poll() calls in ms (default: 1200000 = 20 minutes)
- `KAFKA_REQUEST_TIMEOUT_MS`: Kafka operation timeout in ms (default: 120000 = 2 minutes)

### Portal Configuration

- `PORTAL_TARGET_API_URL`: Target REST API base URL (required)
- `PORTAL_USE_OAUTH`: Enable OAuth2 (default: true)
- `PORTAL_LOG_LEVEL`: Logging level (default: INFO)
- `PORTAL_MAX_CONCURRENT_JOBS`: Max concurrent jobs (default: 10)
- `PORTAL_JOB_TIMEOUT_SECONDS`: HTTP request timeout in seconds (default: 900 = 15 minutes)
- `PORTAL_JOB_MAX_AGE_SECONDS`: Max job age before cleanup in seconds (default: 900 = 15 minutes)
- `PORTAL_ALLOWED_ENDPOINTS`: Comma-separated endpoint whitelist patterns (default: "" = block all in strict mode)
- `PORTAL_ALLOWED_HEADERS`: Comma-separated allowed header names (default: "Content-Type,Accept,X-Request-ID,X-Correlation-ID")
- `PORTAL_STRICT_SECURITY`: Enable strict security mode (default: true)

### OAuth2 Configuration

- `OAUTH2_TOKEN_URL`: OAuth2 token endpoint (required if OAuth enabled)
- `OAUTH2_CLIENT_ID`: Client ID (required)
- `OAUTH2_CLIENT_SECRET`: Client secret (required)
- `OAUTH2_SCOPE`: OAuth2 scope (optional)
- `OAUTH2_AUDIENCE`: Token audience (optional)

### Long-Running Request Support

KafkaSend is designed to handle REST API requests that take up to 15 minutes to complete. The timeout configuration ensures proper handling:

- **HTTP Request Timeout**: 15 minutes (`PORTAL_JOB_TIMEOUT_SECONDS=900`)
- **Job Cleanup Timeout**: 15 minutes (`PORTAL_JOB_MAX_AGE_SECONDS=900`)
- **Kafka Max Poll Interval**: 20 minutes (`KAFKA_MAX_POLL_INTERVAL_MS=1200000`)

The portal service remains connected to Kafka during long REST requests by sending heartbeats every 3 seconds. Jobs that exceed the timeout are automatically cleaned up and an error response is sent to the client.

For REST APIs that may take longer than 15 minutes, adjust these environment variables:

```bash
# Example: 30-minute timeout
PORTAL_JOB_TIMEOUT_SECONDS=1800
PORTAL_JOB_MAX_AGE_SECONDS=1800
KAFKA_MAX_POLL_INTERVAL_MS=2400000  # 40 minutes (30 min + buffer)
```

See [PROTOCOL.md](PROTOCOL.md#timeouts) for detailed timeout configuration guidance.

## Security

KafkaSend implements multiple security controls to prevent abuse by compromised or malicious clients.

### Security Features

- **Endpoint Whitelisting**: Only allows requests to specific API endpoints
- **Header Filtering**: Blocks unauthorized headers (Authorization, Cookie, etc.)
- **SSRF Protection**: Prevents access to internal services and metadata endpoints
- **Strict Mode**: Configurable enforcement of security policies

### Security Configuration

Configure security settings via environment variables:

```bash
# Endpoint whitelist (comma-separated patterns, supports wildcards)
PORTAL_ALLOWED_ENDPOINTS="/api/upload,/api/documents/*"

# Header whitelist (comma-separated header names)
PORTAL_ALLOWED_HEADERS="Content-Type,X-Request-ID,X-Correlation-ID"

# Strict security mode (true = reject violations, false = log only)
PORTAL_STRICT_SECURITY=true
```

### Production Security Recommendations

1. **Always use endpoint whitelisting** - Never deploy with empty `PORTAL_ALLOWED_ENDPOINTS` in production
2. **Minimize allowed headers** - Only whitelist headers your API actually needs
3. **Enable strict mode** - Set `PORTAL_STRICT_SECURITY=true`
4. **Enable Kafka TLS** - Use encrypted connections to Kafka brokers
5. **Enable OAuth2** - Require authentication for all REST API requests
6. **Network isolation** - Run portal in isolated network segment
7. **Monitor logs** - Alert on security validation failures

### Example: Secure Production Configuration

```bash
# Target API
PORTAL_TARGET_API_URL=https://api.production.example.com

# Security: Strict whitelist
PORTAL_ALLOWED_ENDPOINTS="/api/v1/upload,/api/v1/documents/*"
PORTAL_ALLOWED_HEADERS="Content-Type,X-Request-ID"
PORTAL_STRICT_SECURITY=true

# OAuth2 Authentication
PORTAL_USE_OAUTH=true
OAUTH2_TOKEN_URL=https://auth.example.com/oauth/token
OAUTH2_CLIENT_ID=portal-service
OAUTH2_CLIENT_SECRET=<secret>

# Kafka with TLS
KAFKA_BOOTSTRAP_SERVERS=kafka-broker:9093
```

### Security Testing

The project includes comprehensive security tests:

```bash
# Run security tests
pytest tests/test_security.py -v

# Expected results:
# - Whitelisted endpoints pass
# - Non-whitelisted endpoints blocked
# - Forbidden headers removed
# - SSRF patterns blocked
```

See [PROTOCOL.md Security Considerations](PROTOCOL.md#security-considerations) for detailed security documentation.

## Project Structure

```
kafkasend/
├── src/kafkasend/
│   ├── common/          # Shared utilities, models, configuration
│   ├── portal/          # Portal service (bridge)
│   └── client/          # Client CLI
├── docker/              # Docker configuration
├── config/              # Environment file examples
└── tests/               # Unit and integration tests
```

## Testing

```bash
# Run tests
pytest tests/

# With coverage
pytest --cov=kafkasend tests/
```

## Commands

Use the provided Makefile for common tasks:

```bash
make install        # Install package
make test          # Run tests
make docker-up     # Start Docker services
make docker-down   # Stop Docker services
```

## License

MIT License - see LICENSE file for details.
