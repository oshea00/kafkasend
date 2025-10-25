# KafkaSend

A Kafka-to-REST API bridge that enables sending large files (up to 50MB+) and HTTP requests through Kafka topics with automatic chunking, OAuth2 authentication support, and response streaming.

## Overview

KafkaSend consists of two main components:

1. **Portal Service**: A bridge service that listens on Kafka topics for requests, accumulates chunked messages, makes REST API calls (with OAuth2 JWT authentication), and streams responses back via Kafka.

2. **Client CLI**: A command-line tool that sends files and HTTP requests to the portal via Kafka, automatically chunking large files and reassembling responses.

## Features

- **Large File Support**: Handles files up to 50MB+ by automatically chunking them into Kafka-compatible message sizes
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

# Send file using Docker client
docker-compose run --rm client send-file \
  /testdata/hello.txt \
  --endpoint /api/upload \
  --method POST
```

### 3. Stop services

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

### Portal Configuration

- `PORTAL_TARGET_API_URL`: Target REST API base URL (required)
- `PORTAL_USE_OAUTH`: Enable OAuth2 (default: true)
- `PORTAL_LOG_LEVEL`: Logging level (default: INFO)
- `PORTAL_MAX_CONCURRENT_JOBS`: Max concurrent jobs (default: 10)

### OAuth2 Configuration

- `OAUTH2_TOKEN_URL`: OAuth2 token endpoint (required if OAuth enabled)
- `OAUTH2_CLIENT_ID`: Client ID (required)
- `OAUTH2_CLIENT_SECRET`: Client secret (required)
- `OAUTH2_SCOPE`: OAuth2 scope (optional)
- `OAUTH2_AUDIENCE`: Token audience (optional)

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
