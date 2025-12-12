#!/usr/bin/env python3
"""
ado_client.py - Azure DevOps REST API client with rate limiting and batch support.

Industry best practices implemented:
- Batch operations (up to 200 work items per request)
- Rate limit handling via X-RateLimit-* and Retry-After headers
- Exponential backoff with jitter for transient failures
- Structured error types for different failure modes
- Connection pooling via requests.Session

References:
- https://learn.microsoft.com/en-us/azure/devops/integrate/concepts/rate-limits
- https://learn.microsoft.com/en-us/azure/devops/integrate/concepts/integration-bestpractices
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Optional, List, Dict, Tuple, Union
from urllib.parse import urljoin
import random

# Try to import requests, fall back to urllib if not available
try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    import urllib.request
    import urllib.error
    HAS_REQUESTS = False


class ErrorType(Enum):
    """Categorized error types for appropriate handling."""
    TRANSIENT = "transient"           # Retry with backoff
    RATE_LIMITED = "rate_limited"     # Retry after delay
    AUTH_FAILED = "auth_failed"       # Re-authenticate
    NOT_FOUND = "not_found"           # Resource doesn't exist
    VALIDATION = "validation"         # Bad request, don't retry
    PERMISSION = "permission"         # Access denied
    UNKNOWN = "unknown"               # Unexpected error


@dataclass
class ADOError(Exception):
    """Structured error with type classification for appropriate handling."""
    error_type: ErrorType
    message: str
    status_code: Optional[int] = None
    retry_after: Optional[int] = None
    details: Optional[dict] = None

    def __str__(self):
        parts = [f"[{self.error_type.value}] {self.message}"]
        if self.status_code:
            parts.append(f"(HTTP {self.status_code})")
        if self.retry_after:
            parts.append(f"Retry after: {self.retry_after}s")
        return " ".join(parts)

    @property
    def is_retryable(self) -> bool:
        return self.error_type in (ErrorType.TRANSIENT, ErrorType.RATE_LIMITED)


@dataclass
class RateLimitInfo:
    """Rate limit status from response headers."""
    limit: Optional[int] = None
    remaining: Optional[int] = None
    reset: Optional[int] = None
    delay: Optional[float] = None
    retry_after: Optional[int] = None

    @classmethod
    def from_headers(cls, headers: dict) -> "RateLimitInfo":
        """Parse rate limit info from response headers."""
        return cls(
            limit=int(headers.get("X-RateLimit-Limit", 0)) or None,
            remaining=int(headers.get("X-RateLimit-Remaining", 0)) or None,
            reset=int(headers.get("X-RateLimit-Reset", 0)) or None,
            delay=float(headers.get("X-RateLimit-Delay", 0)) or None,
            retry_after=int(headers.get("Retry-After", 0)) or None,
        )

    @property
    def should_slow_down(self) -> bool:
        """Check if we're approaching rate limits."""
        if self.remaining is not None and self.limit is not None:
            return self.remaining < (self.limit * 0.2)  # Less than 20% remaining
        return False


@dataclass
class ADOConfig:
    """Azure DevOps configuration."""
    organization: str
    project: str
    api_version: str = "7.1"

    @property
    def org_url(self) -> str:
        """Get normalized organization URL."""
        org = self.organization
        if not org.startswith("http"):
            org = f"https://dev.azure.com/{org}"
        return org.rstrip("/")

    @property
    def project_url(self) -> str:
        """Get project-scoped URL."""
        return f"{self.org_url}/{self.project}"

    @classmethod
    def from_file(cls, config_path: str) -> "ADOConfig":
        """Load configuration from JSON file."""
        data = json.loads(Path(config_path).read_text())
        return cls(
            organization=data["organization"],
            project=data["project"],
            api_version=data.get("api_version", "7.1")
        )


class ADOClient:
    """
    Azure DevOps REST API client with rate limiting and batch support.

    Best practices implemented:
    1. Batch operations for work items (max 200 per request)
    2. Rate limit tracking via response headers
    3. Exponential backoff with jitter for retries
    4. Proper error categorization
    """

    BATCH_SIZE = 200  # Azure DevOps maximum
    MAX_RETRIES = 3
    BASE_DELAY = 1.0  # Base delay for exponential backoff
    MAX_DELAY = 60.0  # Maximum delay between retries

    def __init__(self, config: ADOConfig, verbose: bool = False):
        self.config = config
        self.verbose = verbose
        self._access_token: Optional[str] = None
        self._token_expires: Optional[datetime] = None
        self._rate_limit_info: Optional[RateLimitInfo] = None

        if HAS_REQUESTS:
            self._session = requests.Session()
            self._session.headers.update({
                "Content-Type": "application/json",
                "Accept": "application/json"
            })

    def _log(self, message: str):
        """Log message if verbose mode enabled."""
        if self.verbose:
            print(f"[ADO] {message}", file=sys.stderr)

    def _get_access_token(self) -> str:
        """Get Azure AD access token via Azure CLI."""
        # Check if token is still valid (with 5-minute buffer)
        if self._access_token and self._token_expires:
            if datetime.now() < self._token_expires:
                return self._access_token

        self._log("Refreshing access token...")

        # Use az account get-access-token for Azure DevOps resource
        # Resource ID: 499b84ac-1321-427f-aa17-267ca6975798 is Azure DevOps
        result = subprocess.run(
            ["az", "account", "get-access-token",
             "--resource", "499b84ac-1321-427f-aa17-267ca6975798",
             "--output", "json"],
            capture_output=True, text=True, timeout=30
        )

        if result.returncode != 0:
            raise ADOError(
                error_type=ErrorType.AUTH_FAILED,
                message=f"Failed to get access token: {result.stderr}",
                details={"stderr": result.stderr}
            )

        token_data = json.loads(result.stdout)
        self._access_token = token_data["accessToken"]

        # Parse expiration time
        expires_on = token_data.get("expiresOn")
        if expires_on:
            # Parse ISO format with timezone
            try:
                from datetime import timezone
                self._token_expires = datetime.fromisoformat(expires_on.replace("Z", "+00:00"))
            except:
                # Default to 50 minutes from now
                from datetime import timedelta
                self._token_expires = datetime.now() + timedelta(minutes=50)

        return self._access_token

    def _calculate_backoff(self, attempt: int, retry_after: Optional[int] = None) -> float:
        """Calculate delay with exponential backoff and jitter."""
        if retry_after:
            return retry_after

        # Exponential backoff: base * 2^attempt
        delay = self.BASE_DELAY * (2 ** attempt)
        # Add jitter (±25%)
        jitter = delay * 0.25 * (2 * random.random() - 1)
        delay = min(delay + jitter, self.MAX_DELAY)

        return delay

    def _classify_error(self, status_code: int, response_body: str = "") -> ErrorType:
        """Classify HTTP error into appropriate error type."""
        if status_code == 429:
            return ErrorType.RATE_LIMITED
        elif status_code == 401:
            return ErrorType.AUTH_FAILED
        elif status_code == 403:
            return ErrorType.PERMISSION
        elif status_code == 404:
            return ErrorType.NOT_FOUND
        elif status_code == 400:
            return ErrorType.VALIDATION
        elif status_code >= 500:
            return ErrorType.TRANSIENT
        elif status_code in (408, 502, 503, 504):
            return ErrorType.TRANSIENT
        return ErrorType.UNKNOWN

    def _make_request(
        self,
        method: str,
        url: str,
        data: Optional[dict] = None,
        params: Optional[dict] = None
    ) -> tuple[dict, RateLimitInfo]:
        """Make HTTP request with retry logic and rate limit handling."""

        headers = {
            "Authorization": f"Bearer {self._get_access_token()}",
            "Content-Type": "application/json",
            "Accept": "application/json"
        }

        # Add API version to params
        if params is None:
            params = {}
        params["api-version"] = self.config.api_version

        last_error: Optional[ADOError] = None

        for attempt in range(self.MAX_RETRIES + 1):
            try:
                # Check if we should slow down based on previous rate limit info
                if self._rate_limit_info and self._rate_limit_info.should_slow_down:
                    delay = 1.0  # Small delay when approaching limits
                    self._log(f"Approaching rate limit, sleeping {delay}s")
                    time.sleep(delay)

                self._log(f"Request {method} {url} (attempt {attempt + 1})")

                if HAS_REQUESTS:
                    response = self._session.request(
                        method=method,
                        url=url,
                        headers=headers,
                        params=params,
                        json=data,
                        timeout=60
                    )

                    # Update rate limit info from headers
                    self._rate_limit_info = RateLimitInfo.from_headers(dict(response.headers))

                    if response.status_code == 200:
                        return response.json(), self._rate_limit_info

                    # Handle errors
                    error_type = self._classify_error(response.status_code, response.text)
                    error = ADOError(
                        error_type=error_type,
                        message=f"API request failed: {response.text[:500]}",
                        status_code=response.status_code,
                        retry_after=self._rate_limit_info.retry_after
                    )

                    if not error.is_retryable or attempt >= self.MAX_RETRIES:
                        raise error

                    last_error = error
                    delay = self._calculate_backoff(attempt, error.retry_after)
                    self._log(f"Retryable error, sleeping {delay:.1f}s before retry")
                    time.sleep(delay)

                else:
                    # Fallback to urllib
                    import urllib.request
                    full_url = url + "?" + "&".join(f"{k}={v}" for k, v in params.items())
                    req = urllib.request.Request(
                        full_url,
                        data=json.dumps(data).encode() if data else None,
                        headers=headers,
                        method=method
                    )

                    with urllib.request.urlopen(req, timeout=60) as resp:
                        response_data = json.loads(resp.read().decode())
                        rate_info = RateLimitInfo.from_headers(dict(resp.headers))
                        return response_data, rate_info

            except ADOError:
                raise
            except requests.exceptions.Timeout if HAS_REQUESTS else Exception as e:
                error = ADOError(
                    error_type=ErrorType.TRANSIENT,
                    message=f"Request timeout: {e}"
                )
                if attempt >= self.MAX_RETRIES:
                    raise error
                last_error = error
                delay = self._calculate_backoff(attempt)
                self._log(f"Timeout, sleeping {delay:.1f}s before retry")
                time.sleep(delay)
            except Exception as e:
                raise ADOError(
                    error_type=ErrorType.UNKNOWN,
                    message=str(e)
                )

        raise last_error or ADOError(ErrorType.UNKNOWN, "Max retries exceeded")

    def get_work_items_batch(
        self,
        ids: list[int],
        fields: Optional[list[str]] = None,
        expand: str = "None"
    ) -> list[dict]:
        """
        Get work items using batch API (max 200 per request).

        This is the recommended approach per Microsoft best practices:
        https://learn.microsoft.com/en-us/azure/devops/integrate/concepts/integration-bestpractices

        Args:
            ids: List of work item IDs (will be batched automatically)
            fields: Optional list of fields to return (reduces payload)
            expand: Expansion options: None, Relations, Fields, Links, All

        Returns:
            List of work item dictionaries
        """
        if not ids:
            return []

        all_items = []

        # Process in batches of BATCH_SIZE (200)
        for i in range(0, len(ids), self.BATCH_SIZE):
            batch_ids = ids[i:i + self.BATCH_SIZE]
            self._log(f"Fetching batch {i // self.BATCH_SIZE + 1} ({len(batch_ids)} items)")

            url = f"{self.config.org_url}/_apis/wit/workitemsbatch"

            body = {
                "ids": batch_ids,
                "$expand": expand,
                "errorPolicy": "Omit"  # Skip invalid IDs instead of failing
            }

            if fields:
                body["fields"] = fields

            response, _ = self._make_request("POST", url, data=body)

            items = response.get("value", [])
            all_items.extend(items)

        return all_items

    def query_work_items(
        self,
        wiql: str,
        fields: Optional[list[str]] = None,
        max_results: int = 1000,
        fetch_details: bool = True
    ) -> list[dict]:
        """
        Execute WIQL query and optionally fetch work item details.

        Best practice: Use batch API to fetch details instead of N+1 queries.

        Args:
            wiql: WIQL query string
            fields: Fields to retrieve (if fetch_details=True)
            max_results: Maximum results to return (caps at 20000)
            fetch_details: Whether to fetch full work item details

        Returns:
            List of work items (IDs only if fetch_details=False)
        """
        # Clean up WIQL
        wiql_clean = " ".join(wiql.split())

        # Add TOP clause if not present and max_results specified
        if "TOP " not in wiql_clean.upper() and max_results:
            wiql_clean = wiql_clean.replace(
                "SELECT ",
                f"SELECT TOP {min(max_results, 20000)} ",
                1
            )

        url = f"{self.config.project_url}/_apis/wit/wiql"
        body = {"query": wiql_clean}

        response, _ = self._make_request("POST", url, data=body)

        # Extract work item IDs from result
        work_items = response.get("workItems", [])
        ids = [wi["id"] for wi in work_items if "id" in wi]

        if not fetch_details:
            return [{"id": id} for id in ids]

        if not ids:
            return []

        # Use batch API to fetch details (the efficient way!)
        return self.get_work_items_batch(ids, fields=fields)

    def get_work_item(self, item_id: int, expand: str = "All") -> Optional[dict]:
        """Get a single work item by ID."""
        items = self.get_work_items_batch([item_id], expand=expand)
        return items[0] if items else None

    def create_work_item(
        self,
        work_item_type: str,
        title: str,
        fields: Optional[dict] = None
    ) -> dict:
        """Create a new work item."""
        url = f"{self.config.project_url}/_apis/wit/workitems/${work_item_type}"

        # Build JSON Patch document
        operations = [
            {"op": "add", "path": "/fields/System.Title", "value": title}
        ]

        if fields:
            for field_name, value in fields.items():
                if not field_name.startswith("/fields/"):
                    field_name = f"/fields/{field_name}"
                operations.append({"op": "add", "path": field_name, "value": value})

        # Use special content type for patch
        headers = {"Content-Type": "application/json-patch+json"}

        response, _ = self._make_request("POST", url, data=operations)
        return response

    def update_work_item(self, item_id: int, updates: dict) -> dict:
        """Update an existing work item."""
        url = f"{self.config.org_url}/_apis/wit/workitems/{item_id}"

        operations = []
        for field_name, value in updates.items():
            if not field_name.startswith("/fields/"):
                field_name = f"/fields/{field_name}"
            operations.append({"op": "replace", "path": field_name, "value": value})

        response, _ = self._make_request("PATCH", url, data=operations)
        return response


# Convenience functions for CLI usage
def load_client(config_path: str = ".ado/config.json", verbose: bool = False) -> ADOClient:
    """Load ADO client from config file."""
    config = ADOConfig.from_file(config_path)
    return ADOClient(config, verbose=verbose)


def format_work_item(item: dict, include_fields: Optional[list[str]] = None) -> dict:
    """Format work item for output."""
    fields = item.get("fields", {})
    assigned = fields.get("System.AssignedTo")

    result = {
        "id": item.get("id"),
        "url": item.get("url"),
        "title": fields.get("System.Title"),
        "state": fields.get("System.State"),
        "workItemType": fields.get("System.WorkItemType"),
        "assignedTo": assigned.get("displayName") if isinstance(assigned, dict) else assigned,
        "areaPath": fields.get("System.AreaPath"),
        "iterationPath": fields.get("System.IterationPath"),
        "changedDate": fields.get("System.ChangedDate"),
        "priority": fields.get("Microsoft.VSTS.Common.Priority"),
        "tags": fields.get("System.Tags"),
    }

    if include_fields:
        for field in include_fields:
            if field not in result and field in fields:
                result[field] = fields[field]

    return result


if __name__ == "__main__":
    # Self-test
    import argparse

    parser = argparse.ArgumentParser(description="Test ADO client")
    parser.add_argument("--config", "-c", default=".ado/config.json")
    parser.add_argument("--verbose", "-v", action="store_true")
    parser.add_argument("--test", choices=["query", "batch"], default="query")
    args = parser.parse_args()

    try:
        client = load_client(args.config, verbose=args.verbose)

        if args.test == "query":
            wiql = """
                SELECT [System.Id], [System.Title] FROM workitems
                WHERE [System.AssignedTo] = @Me AND [System.State] <> 'Closed'
            """
            items = client.query_work_items(wiql, max_results=10)
            print(json.dumps([format_work_item(i) for i in items], indent=2))

        elif args.test == "batch":
            # Test batch fetch with sample IDs
            items = client.get_work_items_batch([1, 2, 3])
            print(json.dumps([format_work_item(i) for i in items], indent=2))

    except ADOError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
