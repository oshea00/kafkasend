"""Configuration management using Pydantic settings."""

from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class KafkaConfig(BaseSettings):
    """Kafka connection configuration."""

    model_config = SettingsConfigDict(env_prefix='KAFKA_')

    bootstrap_servers: str = "localhost:9092"
    request_topic: str = "api-requests"
    response_topic: str = "api-responses"
    consumer_group: str = "kafkasend-portal"
    auto_offset_reset: str = "earliest"
    session_timeout_ms: int = 30000
    max_poll_records: int = 10


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
    job_timeout_seconds: int = 300


class ClientConfig(BaseSettings):
    """Client configuration."""

    model_config = SettingsConfigDict(env_prefix='CLIENT_')

    log_level: str = "INFO"
