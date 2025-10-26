# KafkaSend Project Guidelines

## Project Overview

KafkaSend is a Kafka-to-REST API bridge that enables sending large files (up to 50MB+) and HTTP requests through Kafka topics with automatic chunking, OAuth2 authentication, bidirectional streaming, and comprehensive security controls.

### Core Purpose

Bridge the gap between Kafka-based messaging systems and REST APIs, allowing:
- Large file transfers through Kafka's message size limits via intelligent chunking
- Multiple concurrent jobs with guaranteed message ordering per job
- Long-running REST API requests (up to 15 minutes)
- Secure request validation to prevent SSRF and header injection attacks
- Bidirectional chunking (client→portal and portal→client)

## Architecture Principles

### 1. Message-Oriented Design
- **Job-based correlation**: Every request has a unique UUID v4 job_id
- **Partition key routing**: All messages for the same job go to the same Kafka partition
- **Consumer groups**: Multiple portal instances can process jobs in parallel
- **Message ordering**: Kafka guarantees order within a partition

### 2. Chunking Strategy
- **Chunk size**: 650KB (before base64 encoding)
- **Rationale**: 650KB × 1.33 (base64 overhead) + JSON envelope ≈ 870KB < 1MB Kafka limit
- **Bidirectional**: Both requests and responses can be chunked
- **Reassembly**: Track sequence numbers and total_chunks to reassemble

### 3. State Management
- **In-memory only**: No persistence, chunks stored in RAM during processing
- **Timeout-based cleanup**: Jobs exceeding max age are automatically cleaned up
- **Activity tracking**: Monitor both job age and idle time

### 4. Security-First
- **Default deny**: Strict security mode enabled by default
- **Whitelist-based**: Both endpoints and headers use explicit allow-lists
- **Defense in depth**: Multiple layers (endpoint validation, header filtering, SSRF protection)
- **OAuth separation**: Portal manages authentication, clients cannot override

## Security Requirements

### Mandatory Security Controls

1. **Endpoint Whitelisting** (REQUIRED for production)
   ```bash
   PORTAL_ALLOWED_ENDPOINTS="/api/v1/upload,/api/v1/documents/*"
   ```
   - Use specific patterns, avoid wildcards like `/*` in production
   - Test all patterns thoroughly
   - Never deploy with empty whitelist in production

2. **Header Filtering** (REQUIRED)
   ```bash
   PORTAL_ALLOWED_HEADERS="Content-Type,X-Request-ID,X-Correlation-ID"
   ```
   - Only allow headers your API actually needs
   - Never allow: Authorization, Cookie, Proxy-Authorization, X-Forwarded-For

3. **SSRF Protection** (AUTOMATIC)
   - Blocks localhost, 127.0.0.1, ::1
   - Blocks cloud metadata endpoints (169.254.169.254)
   - Blocks private network ranges (10.*, 172.16.*, 192.168.*)
   - Cannot be disabled

4. **Strict Mode** (REQUIRED for production)
   ```bash
   PORTAL_STRICT_SECURITY=true
   ```
   - Rejects invalid requests with error responses
   - Logs all security violations

### Security Testing Requirements

Every security control MUST have tests:
- Valid requests pass through
- Invalid endpoints are blocked
- Forbidden headers are removed
- SSRF patterns are detected
- Empty whitelists behave correctly

See `tests/test_security.py` for reference implementation.

## Performance Requirements

### Timeout Configuration

Long-running REST API requests (up to 15 minutes) require coordinated timeout settings:

```bash
# HTTP request timeout (15 minutes)
PORTAL_JOB_TIMEOUT_SECONDS=900

# Job cleanup timeout (15 minutes)
PORTAL_JOB_MAX_AGE_SECONDS=900

# Kafka max poll interval (20 minutes - must be > job timeout)
KAFKA_MAX_POLL_INTERVAL_MS=1200000

# Kafka session timeout (5 minutes)
KAFKA_SESSION_TIMEOUT_MS=300000
```

**Critical Relationship**: `max_poll_interval_ms` must be greater than `job_timeout_seconds` to prevent consumer from being kicked out during long REST requests.

### Scaling Guidelines

1. **Partition Count**: Create topics with multiple partitions for parallel processing
2. **Portal Instances**: Run multiple portal containers with same consumer group
3. **Job Affinity**: Job ID partition key ensures all chunks go to same portal instance
4. **Concurrent Jobs**: Limit per-portal concurrent jobs to prevent memory exhaustion

## Code Quality Standards

### Python Code Style

1. **Type Hints**: Use type hints for all function signatures
   ```python
   def process_job(job: JobState) -> Optional[Response]:
   ```

2. **Pydantic v2**: Use `ConfigDict` not `class Config`
   ```python
   from pydantic import BaseModel, ConfigDict

   class MyModel(BaseModel):
       field: str
       model_config = ConfigDict(use_enum_values=True)
   ```

3. **Structured Logging**: Use structlog with context
   ```python
   logger.info("Job started", job_id=job_id, endpoint=endpoint)
   ```

4. **Error Handling**: Catch specific exceptions, log with context
   ```python
   try:
       response = execute_request(job)
   except requests.Timeout as e:
       logger.error("Request timeout", job_id=job.job_id, error=str(e))
       send_error_response(job.job_id, f"Request timeout: {e}")
   ```

### Configuration Management

1. **Environment Variables**: All configuration via env vars with `COMPONENT_` prefix
   - Kafka: `KAFKA_*`
   - Portal: `PORTAL_*`
   - OAuth: `OAUTH2_*`
   - Client: `CLIENT_*`

2. **Defaults**: Provide secure defaults
   - Security: Strict mode ON
   - Timeouts: Conservative values (15 minutes)
   - Headers: Minimal whitelist

3. **Validation**: Use Pydantic validators for complex validation
   ```python
   @field_validator('allowed_endpoints')
   @classmethod
   def parse_allowed_endpoints(cls, v: str) -> str:
       return v.strip()
   ```

## Testing Requirements

### Test Coverage Standards

All code must have test coverage for:

1. **Happy Path**: Normal operation succeeds
2. **Error Cases**: Failures handled gracefully
3. **Edge Cases**: Empty inputs, max sizes, boundary conditions
4. **Security**: Invalid requests blocked, valid requests pass

### Required Test Types

1. **Unit Tests**: Test individual functions/methods
   - Security validation logic
   - Chunking and reassembly
   - Job state management

2. **Integration Tests**: Test component interactions
   - Kafka message flow
   - REST API calls
   - OAuth token management

3. **Security Tests**: Test all security controls
   - Endpoint whitelisting
   - Header filtering
   - SSRF protection
   - Strict mode enforcement

### Test Organization

```
tests/
├── test_security.py        # Security validation tests
├── test_chunking.py        # Chunking and reassembly
├── test_job_manager.py     # Job state management
├── test_rest_client.py     # REST API interactions
└── test_integration.py     # End-to-end flows
```

## Documentation Standards

### Code Documentation

1. **Docstrings**: All public functions, classes, methods
   ```python
   def validate_endpoint(self, endpoint: str) -> Tuple[bool, Optional[str]]:
       """
       Validate if endpoint is allowed.

       Args:
           endpoint: Requested endpoint path

       Returns:
           Tuple of (is_valid, error_message)
       """
   ```

2. **Comments**: Explain WHY, not WHAT
   ```python
   # Use job_id as partition key to ensure all messages for the same job
   # go to the same partition (and thus the same portal instance)
   self._producer.send(topic, key=job_id.encode('utf-8'), value=data)
   ```

3. **Type Hints**: Serve as inline documentation
   ```python
   def cleanup_stale_jobs(self, max_age_seconds: float) -> List[Tuple[str, str]]:
   ```

### Project Documentation

1. **README.md**: User-facing, getting started guide
   - Quick start with Docker
   - Configuration reference
   - Security overview
   - Production deployment tips

2. **PROTOCOL.md**: Technical specification
   - Message format definitions
   - Sequence diagrams
   - Timeout configuration
   - Security controls
   - Performance characteristics

3. **CLAUDE.md** (this file): Development guidelines
   - Architecture principles
   - Security requirements
   - Code standards
   - Testing requirements

## Development Workflow

### Adding New Features

1. **Update Tests First** (TDD when possible)
   - Write test cases for new functionality
   - Include security tests if applicable
   - Test both success and failure paths

2. **Implement Feature**
   - Follow code style guidelines
   - Add appropriate logging
   - Handle errors gracefully
   - Use type hints

3. **Update Configuration**
   - Add new env vars to config.py
   - Provide sensible defaults
   - Document in README.md

4. **Update Documentation**
   - README.md for user-facing features
   - PROTOCOL.md for protocol changes
   - Docstrings for all new code
   - Update CLAUDE.md if architecture changes

5. **Test Thoroughly**
   - Run all tests: `pytest tests/`
   - Test with Docker Compose
   - Verify security controls still work

### Security Checklist for Changes

Before merging any PR:

- [ ] Endpoint validation still works
- [ ] Header filtering still works
- [ ] SSRF protection not bypassed
- [ ] No new headers added to allowed list without justification
- [ ] No relaxation of security defaults
- [ ] Security tests updated if security logic changed
- [ ] Production configuration example updated

### Configuration Changes Checklist

- [ ] New env var documented in README.md
- [ ] Default value is secure
- [ ] Pydantic model includes proper type hints
- [ ] Validator added if complex validation needed
- [ ] docker-compose.yml updated with example
- [ ] PROTOCOL.md updated if affects behavior

## Common Pitfalls and Solutions

### 1. Message Size Errors

**Problem**: `MessageSizeTooLargeError` when sending messages

**Cause**: Base64 encoding increases size by ~33%

**Solution**: Keep chunk size at 650KB or lower

### 2. Consumer Kicked Out

**Problem**: Consumer removed from group during long REST request

**Cause**: `max_poll_interval_ms` too short

**Solution**: Set `max_poll_interval_ms` > `job_timeout_seconds` + buffer

### 3. Headers Not Filtering

**Problem**: Client headers passing through unfiltered

**Cause**: Empty whitelist logic incorrect

**Solution**: Ensure empty whitelist blocks ALL headers

### 4. SSRF Bypass Attempt

**Problem**: Clever encoding tries to bypass SSRF filters

**Solution**: Apply SSRF checks BEFORE any URL decoding, use comprehensive pattern list

### 5. Job Memory Leak

**Problem**: Jobs accumulating in memory

**Cause**: Cleanup not running or timeout too long

**Solution**: Periodic cleanup (every 60s), reasonable max_age_seconds

## Future Enhancement Considerations

When adding new features, consider:

1. **Backward Compatibility**: Can existing clients still work?
2. **Security Impact**: Does this create new attack vectors?
3. **Performance Impact**: Does this affect throughput or latency?
4. **Configuration Complexity**: Can users configure this reasonably?
5. **Testing Complexity**: Can this be tested reliably?

### Potential Future Work

- **Async Processing**: Decouple request receipt from REST API execution
- **Persistent Storage**: Store chunks in Redis/S3 for very large files
- **Compression**: Compress chunks before base64 encoding
- **Rate Limiting**: Per-client rate limits
- **Metrics**: Prometheus metrics for monitoring
- **Tracing**: Distributed tracing with OpenTelemetry
- **Dead Letter Queue**: Failed jobs sent to DLQ for investigation

## Version Compatibility

### Python
- Minimum: Python 3.9
- Tested: Python 3.11
- Target: Python 3.12+

### Pydantic
- Use: Pydantic v2
- Avoid: `class Config` (deprecated)
- Use: `ConfigDict` for model configuration

### Kafka
- Client: kafka-python
- Broker: Kafka 2.8+
- Protocol: Partition keys required for job affinity

### Docker
- Compose: v3.8+
- Base Images: Python 3.11-slim for production

## Contact and Collaboration

When working on this project:

1. **Read PROTOCOL.md first** - Understand the message protocol
2. **Check security tests** - Ensure security controls work
3. **Test with Docker Compose** - Verify in realistic environment
4. **Update documentation** - Keep docs in sync with code
5. **Ask questions** - Better to clarify than make assumptions

---

**Last Updated**: 2025
**Project Status**: Production-ready with comprehensive security controls
**Maintainer Guidelines**: Follow security-first principles, maintain test coverage, document everything
