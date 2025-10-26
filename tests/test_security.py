"""Tests for security validation."""

import pytest
from kafkasend.portal.security import SecurityValidator
from kafkasend.common.config import PortalConfig


@pytest.fixture
def strict_config():
    """Config with strict security enabled."""
    return PortalConfig(
        target_api_url="https://api.example.com",
        allowed_endpoints="/api/upload,/api/documents/*",
        allowed_headers="Content-Type,X-Request-ID",
        strict_security=True
    )


@pytest.fixture
def permissive_config():
    """Config with permissive security (for testing)."""
    return PortalConfig(
        target_api_url="https://api.example.com",
        allowed_endpoints="",
        allowed_headers="",
        strict_security=False
    )


class TestEndpointValidation:
    """Test endpoint validation."""

    def test_allowed_exact_match(self, strict_config):
        """Test exact match is allowed."""
        validator = SecurityValidator(strict_config)
        is_valid, error = validator.validate_endpoint("/api/upload")
        assert is_valid
        assert error is None

    def test_allowed_wildcard_match(self, strict_config):
        """Test wildcard pattern match."""
        validator = SecurityValidator(strict_config)
        is_valid, error = validator.validate_endpoint("/api/documents/123")
        assert is_valid
        assert error is None

    def test_blocked_not_in_whitelist(self, strict_config):
        """Test endpoint not in whitelist is blocked."""
        validator = SecurityValidator(strict_config)
        is_valid, error = validator.validate_endpoint("/admin/users")
        assert not is_valid
        assert "not in whitelist" in error

    def test_ssrf_localhost_blocked(self, strict_config):
        """Test localhost SSRF attempt is blocked."""
        validator = SecurityValidator(strict_config)
        is_valid, error = validator.validate_endpoint("localhost")
        assert not is_valid
        assert "SSRF" in error

    def test_ssrf_metadata_blocked(self, strict_config):
        """Test AWS metadata endpoint is blocked."""
        validator = SecurityValidator(strict_config)
        is_valid, error = validator.validate_endpoint("169.254.169.254")
        assert not is_valid
        assert "SSRF" in error

    def test_no_whitelist_strict_mode(self):
        """Test no whitelist in strict mode blocks all."""
        config = PortalConfig(
            target_api_url="https://api.example.com",
            allowed_endpoints="",
            strict_security=True
        )
        validator = SecurityValidator(config)
        is_valid, error = validator.validate_endpoint("/api/upload")
        assert not is_valid
        assert "No endpoint whitelist" in error

    def test_no_whitelist_permissive_mode(self, permissive_config):
        """Test no whitelist in permissive mode allows all (with warning)."""
        validator = SecurityValidator(permissive_config)
        is_valid, error = validator.validate_endpoint("/api/upload")
        assert is_valid
        assert error is None


class TestHeaderValidation:
    """Test header validation."""

    def test_allowed_headers_pass(self, strict_config):
        """Test allowed headers pass through."""
        validator = SecurityValidator(strict_config)
        headers = {
            "Content-Type": "application/json",
            "X-Request-ID": "123"
        }
        filtered, removed = validator.validate_and_filter_headers(headers)
        assert len(filtered) == 2
        assert "Content-Type" in filtered
        assert "X-Request-ID" in filtered
        assert len(removed) == 0

    def test_disallowed_header_blocked(self, strict_config):
        """Test disallowed header is removed."""
        validator = SecurityValidator(strict_config)
        headers = {
            "Content-Type": "application/json",
            "X-Custom-Header": "value"
        }
        filtered, removed = validator.validate_and_filter_headers(headers)
        assert len(filtered) == 1
        assert "Content-Type" in filtered
        assert "X-Custom-Header" not in filtered
        assert "X-Custom-Header" in removed

    def test_forbidden_header_blocked(self, strict_config):
        """Test forbidden header (Authorization) is always blocked."""
        validator = SecurityValidator(strict_config)
        headers = {
            "Authorization": "Bearer malicious-token",
            "Content-Type": "application/json"
        }
        filtered, removed = validator.validate_and_filter_headers(headers)
        assert "Authorization" not in filtered
        assert "Authorization" in removed
        assert "Content-Type" in filtered

    def test_forbidden_header_cookie_blocked(self, strict_config):
        """Test Cookie header is blocked."""
        validator = SecurityValidator(strict_config)
        headers = {
            "Cookie": "session=xyz",
            "Content-Type": "application/json"
        }
        filtered, removed = validator.validate_and_filter_headers(headers)
        assert "Cookie" not in filtered
        assert "Cookie" in removed

    def test_case_insensitive_matching(self, strict_config):
        """Test header matching is case-insensitive."""
        validator = SecurityValidator(strict_config)
        headers = {
            "content-type": "application/json",
            "X-REQUEST-ID": "123"
        }
        filtered, removed = validator.validate_and_filter_headers(headers)
        assert len(filtered) == 2
        assert len(removed) == 0

    def test_no_whitelist_blocks_all(self):
        """Test empty whitelist blocks all headers."""
        config = PortalConfig(
            target_api_url="https://api.example.com",
            allowed_headers="",
            strict_security=True
        )
        validator = SecurityValidator(config)
        headers = {
            "Content-Type": "application/json",
            "X-Custom": "value"
        }
        filtered, removed = validator.validate_and_filter_headers(headers)
        assert len(filtered) == 0
        assert len(removed) == 2


class TestCompleteRequestValidation:
    """Test complete request validation."""

    def test_valid_request(self, strict_config):
        """Test valid request passes all checks."""
        validator = SecurityValidator(strict_config)
        is_valid, error, filtered = validator.validate_request(
            endpoint="/api/upload",
            headers={"Content-Type": "application/json"}
        )
        assert is_valid
        assert error is None
        assert "Content-Type" in filtered

    def test_invalid_endpoint_fails(self, strict_config):
        """Test invalid endpoint fails validation."""
        validator = SecurityValidator(strict_config)
        is_valid, error, filtered = validator.validate_request(
            endpoint="/admin/delete",
            headers={"Content-Type": "application/json"}
        )
        assert not is_valid
        assert error is not None
        assert filtered == {}

    def test_headers_filtered_on_success(self, strict_config):
        """Test headers are filtered even when endpoint is valid."""
        validator = SecurityValidator(strict_config)
        is_valid, error, filtered = validator.validate_request(
            endpoint="/api/upload",
            headers={
                "Content-Type": "application/json",
                "X-Evil-Header": "malicious",
                "Authorization": "Bearer stolen"
            }
        )
        assert is_valid
        assert "Content-Type" in filtered
        assert "X-Evil-Header" not in filtered
        assert "Authorization" not in filtered
