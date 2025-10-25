"""REST API client for making HTTP requests."""

import io
from typing import Dict, Optional
import requests
import structlog

from kafkasend.common.auth import OAuth2TokenManager
from kafkasend.common.config import OAuth2Config, PortalConfig
from kafkasend.portal.job_manager import JobState

logger = structlog.get_logger(__name__)


class RestApiClient:
    """Client for making REST API requests."""

    def __init__(
        self,
        portal_config: PortalConfig,
        oauth_config: Optional[OAuth2Config] = None
    ):
        """
        Initialize the REST API client.

        Args:
            portal_config: Portal configuration
            oauth_config: OAuth2 configuration (if authentication is needed)
        """
        self.portal_config = portal_config
        self.base_url = portal_config.target_api_url

        if portal_config.use_oauth and oauth_config:
            self.token_manager = OAuth2TokenManager(oauth_config)
        else:
            self.token_manager = None

    def execute_request(self, job: JobState) -> requests.Response:
        """
        Execute HTTP request based on job state.

        Args:
            job: Job state with request details

        Returns:
            HTTP response

        Raises:
            requests.RequestException: If request fails
        """
        url = f"{self.base_url.rstrip('/')}/{job.endpoint.lstrip('/')}"
        method = job.method if isinstance(job.method, str) else job.method.value

        # Prepare headers
        headers = dict(job.headers)

        # Add OAuth token if configured
        if self.token_manager:
            auth_headers = self.token_manager.get_auth_headers()
            headers.update(auth_headers)

        # Prepare request kwargs
        kwargs: Dict = {
            'headers': headers,
            'timeout': self.portal_config.job_timeout_seconds,
        }

        # Handle body/files
        if job.chunks:
            # We have data to send
            complete_data = job.get_complete_data()

            if job.filename and job.content_type:
                # Multipart file upload
                files = {
                    'file': (
                        job.filename,
                        io.BytesIO(complete_data),
                        job.content_type
                    )
                }
                kwargs['files'] = files
                logger.info(
                    "Executing multipart request",
                    job_id=job.job_id,
                    method=method,
                    url=url,
                    filename=job.filename,
                    size=len(complete_data)
                )
            else:
                # Raw body data
                kwargs['data'] = complete_data
                if job.content_type:
                    headers['Content-Type'] = job.content_type
                logger.info(
                    "Executing request with body",
                    job_id=job.job_id,
                    method=method,
                    url=url,
                    size=len(complete_data)
                )
        else:
            # No body data
            logger.info(
                "Executing request without body",
                job_id=job.job_id,
                method=method,
                url=url
            )

        try:
            response = requests.request(method, url, **kwargs)
            logger.info(
                "Request completed",
                job_id=job.job_id,
                status_code=response.status_code,
                content_length=len(response.content)
            )
            return response

        except requests.RequestException as e:
            logger.error(
                "Request failed",
                job_id=job.job_id,
                error=str(e)
            )
            raise
