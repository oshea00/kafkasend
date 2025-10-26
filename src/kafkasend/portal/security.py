"""Security validation for portal requests."""

import fnmatch
from typing import Dict, List, Tuple, Optional
import structlog

from kafkasend.common.config import PortalConfig

logger = structlog.get_logger(__name__)


class SecurityValidator:
    """Validates requests against security policies."""

    # Dangerous headers that should never be allowed from clients
    FORBIDDEN_HEADERS = {
        'authorization',
        'proxy-authorization',
        'cookie',
        'x-forwarded-for',
        'x-real-ip',
        'host',
    }

    # Known SSRF targets to block
    SSRF_PATTERNS = [
        '127.0.0.1',
        'localhost',
        '169.254.169.254',  # AWS metadata
        '::1',
        '0.0.0.0',
        '*.local',
        '*.internal',
        '10.*.*.*',
        '172.16.*.*',
        '192.168.*.*',
    ]

    def __init__(self, config: PortalConfig):
        """
        Initialize security validator.

        Args:
            config: Portal configuration with security settings
        """
        self.config = config
        self.allowed_endpoints = config.get_allowed_endpoints_list()
        self.allowed_headers = config.get_allowed_headers_list()
        self.strict_mode = config.strict_security

        logger.info(
            "Security validator initialized",
            allowed_endpoints=self.allowed_endpoints,
            allowed_headers=self.allowed_headers,
            strict_mode=self.strict_mode
        )

    def validate_endpoint(self, endpoint: str) -> Tuple[bool, Optional[str]]:
        """
        Validate if endpoint is allowed.

        Args:
            endpoint: Requested endpoint path

        Returns:
            Tuple of (is_valid, error_message)
        """
        # Check for obvious SSRF attempts in endpoint
        endpoint_lower = endpoint.lower()
        for pattern in self.SSRF_PATTERNS:
            if fnmatch.fnmatch(endpoint_lower, pattern.lower()):
                error = f"Endpoint blocked: potential SSRF target '{endpoint}'"
                logger.warning("SSRF attempt blocked", endpoint=endpoint, pattern=pattern)
                return False, error

        # If no whitelist configured, allow all (with warning)
        if not self.allowed_endpoints:
            if self.strict_mode:
                logger.warning(
                    "No endpoint whitelist configured in strict mode - blocking all",
                    endpoint=endpoint
                )
                return False, "No endpoint whitelist configured - request denied"
            else:
                logger.warning(
                    "No endpoint whitelist configured - allowing all (INSECURE)",
                    endpoint=endpoint
                )
                return True, None

        # Check against whitelist patterns
        for pattern in self.allowed_endpoints:
            if fnmatch.fnmatch(endpoint, pattern):
                logger.debug("Endpoint allowed", endpoint=endpoint, pattern=pattern)
                return True, None

        # Not in whitelist
        error = f"Endpoint '{endpoint}' not in whitelist: {self.allowed_endpoints}"
        logger.warning(
            "Endpoint blocked by whitelist",
            endpoint=endpoint,
            allowed_patterns=self.allowed_endpoints
        )

        if self.strict_mode:
            return False, error
        else:
            logger.warning("Allowing endpoint despite whitelist (strict_mode=False)")
            return True, None

    def validate_and_filter_headers(
        self, headers: Dict[str, str]
    ) -> Tuple[Dict[str, str], List[str]]:
        """
        Validate and filter headers, removing disallowed ones.

        Args:
            headers: Client-provided headers

        Returns:
            Tuple of (filtered_headers, removed_header_names)
        """
        filtered = {}
        removed = []

        for name, value in headers.items():
            name_lower = name.lower()

            # Block forbidden headers
            if name_lower in self.FORBIDDEN_HEADERS:
                removed.append(name)
                logger.warning(
                    "Forbidden header blocked",
                    header=name,
                    reason="Security: forbidden header type"
                )
                continue

            # Check against whitelist
            # Note: Empty whitelist means block all headers (secure default)
            if name_lower in self.allowed_headers:
                # Header is in whitelist, allow it
                filtered[name] = value
            else:
                # Header not in whitelist (or whitelist is empty), block it
                removed.append(name)
                logger.info(
                    "Header blocked by whitelist",
                    header=name,
                    allowed_headers=self.allowed_headers if self.allowed_headers else "(empty - block all)"
                )

        if removed:
            logger.info(
                "Headers filtered",
                original_count=len(headers),
                filtered_count=len(filtered),
                removed=removed
            )

        return filtered, removed

    def validate_request(
        self, endpoint: str, headers: Dict[str, str]
    ) -> Tuple[bool, Optional[str], Dict[str, str]]:
        """
        Validate complete request (endpoint and headers).

        Args:
            endpoint: Requested endpoint
            headers: Client headers

        Returns:
            Tuple of (is_valid, error_message, filtered_headers)
        """
        # Validate endpoint
        endpoint_valid, endpoint_error = self.validate_endpoint(endpoint)
        if not endpoint_valid:
            return False, endpoint_error, {}

        # Filter headers
        filtered_headers, removed = self.validate_and_filter_headers(headers)

        return True, None, filtered_headers
