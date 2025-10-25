"""OAuth2 authentication utilities."""

import time
from typing import Dict, Optional
from authlib.integrations.requests_client import OAuth2Session
import structlog

from kafkasend.common.config import OAuth2Config

logger = structlog.get_logger(__name__)


class OAuth2TokenManager:
    """Manages OAuth2 token acquisition and refresh."""

    def __init__(self, config: OAuth2Config):
        """
        Initialize the token manager.

        Args:
            config: OAuth2 configuration
        """
        self.config = config
        self._token: Optional[Dict] = None
        self._token_expires_at: float = 0

    def get_token(self) -> str:
        """
        Get a valid access token, refreshing if necessary.

        Returns:
            Valid access token
        """
        if self._needs_refresh():
            self._refresh_token()

        if not self._token:
            raise RuntimeError("Failed to obtain access token")

        return self._token['access_token']

    def _needs_refresh(self) -> bool:
        """Check if token needs to be refreshed."""
        if not self._token:
            return True

        # Refresh if token expires in less than 60 seconds
        return time.time() >= (self._token_expires_at - 60)

    def _refresh_token(self) -> None:
        """Obtain a new access token using client credentials flow."""
        logger.info("Obtaining new access token")

        try:
            client = OAuth2Session(
                client_id=self.config.client_id,
                client_secret=self.config.client_secret,
                scope=self.config.scope,
            )

            token_data = {
                'grant_type': 'client_credentials',
            }

            if self.config.audience:
                token_data['audience'] = self.config.audience

            self._token = client.fetch_token(
                self.config.token_url,
                **token_data
            )

            # Calculate expiration time
            expires_in = self._token.get('expires_in', 3600)
            self._token_expires_at = time.time() + expires_in

            logger.info(
                "Access token obtained successfully",
                expires_in=expires_in
            )

        except Exception as e:
            logger.error("Failed to obtain access token", error=str(e))
            raise

    def get_auth_headers(self) -> Dict[str, str]:
        """
        Get HTTP headers with authorization token.

        Returns:
            Dictionary with Authorization header
        """
        token = self.get_token()
        return {
            'Authorization': f'Bearer {token}'
        }
