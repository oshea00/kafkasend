"""Configuration management using Pydantic settings."""

from typing import Optional, List
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import field_validator


class KafkaConfig(BaseSettings):
    """Kafka connection configuration."""

    model_config = SettingsConfigDict(env_prefix='KAFKA_')

    bootstrap_servers: str = "localhost:9092"
    request_topic: str = "api-requests"
    response_topic: str = "api-responses"
    consumer_group: str = "kafkasend-portal"
    auto_offset_reset: str = "earliest"
    # Session timeout: how long before consumer is considered dead (5 minutes)
    session_timeout_ms: int = 300000
    # Max poll interval: max time between poll() calls before consumer is kicked out (20 minutes)
    # Must be longer than job_timeout to allow for long REST requests
    max_poll_interval_ms: int = 1200000
    max_poll_records: int = 10
    # Request timeout for producer/consumer operations (2 minutes)
    request_timeout_ms: int = 120000


class OAuth2Config(BaseSettings):
    """OAuth2 machine-to-machine configuration."""

    model_config = SettingsConfigDict(env_prefix='OAUTH2_')

    token_url: str
    client_id: str
    client_secret: str
    scope: Optional[str] = None
    audience: Optional[str] = None


class PortalConfig(BaseSettings):
    """Portal service configuration."""

    model_config = SettingsConfigDict(env_prefix='PORTAL_')

    target_api_url: str
    use_oauth: bool = True
    log_level: str = "INFO"
    max_concurrent_jobs: int = 10
    # HTTP request timeout: 15 minutes to support long-running REST requests
    job_timeout_seconds: int = 900
    # Job cleanup timeout: 15 minutes - jobs older than this are cleaned up
    job_max_age_seconds: int = 900

    # Security: URL/Endpoint Whitelisting
    # Comma-separated list of allowed endpoint patterns (supports wildcards)
    # Examples: "/api/*", "/upload", "/v1/*/documents"
    # Empty string = allow all (NOT RECOMMENDED for production)
    allowed_endpoints: str = ""

    # Security: Header Whitelisting
    # Comma-separated list of allowed header names (case-insensitive)
    # OAuth headers (Authorization) are handled separately and should NOT be in this list
    # Examples: "Content-Type,X-Request-ID,X-Correlation-ID"
    # Empty string = block all client headers (recommended default)
    allowed_headers: str = "Content-Type,Accept,X-Request-ID,X-Correlation-ID"

    # Security: Strict mode - if True, reject requests that don't match whitelist
    # If False, log warnings but allow (not recommended for production)
    strict_security: bool = True

    @field_validator('allowed_endpoints')
    @classmethod
    def parse_allowed_endpoints(cls, v: str) -> str:
        """Validate and normalize allowed endpoints."""
        return v.strip()

    @field_validator('allowed_headers')
    @classmethod
    def parse_allowed_headers(cls, v: str) -> str:
        """Validate and normalize allowed headers."""
        return v.strip()

    def get_allowed_endpoints_list(self) -> List[str]:
        """Get list of allowed endpoint patterns."""
        if not self.allowed_endpoints:
            return []
        return [ep.strip() for ep in self.allowed_endpoints.split(',') if ep.strip()]

    def get_allowed_headers_list(self) -> List[str]:
        """Get list of allowed header names (lowercase)."""
        if not self.allowed_headers:
            return []
        return [h.strip().lower() for h in self.allowed_headers.split(',') if h.strip()]


class ClientConfig(BaseSettings):
    """Client configuration."""

    model_config = SettingsConfigDict(env_prefix='CLIENT_')

    log_level: str = "INFO"
