from __future__ import annotations

import asyncio
import logging
import os
from abc import ABC, abstractmethod
from contextlib import suppress
from typing import Any
from urllib.parse import urljoin

import httpx

from griptape_nodes.exe_types.node_types import SuccessFailureNode
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes

logger = logging.getLogger("griptape_nodes")

__all__ = ["GriptapeProxyNode"]


class GriptapeProxyNode(SuccessFailureNode, ABC):
    """Base class for nodes that use the Griptape Cloud v2 async model proxy API.

    This class provides common functionality for nodes that:
    1. Submit generation requests to POST /api/proxy/v2/models/{model_id}
    2. Poll generation status via GET /api/proxy/v2/generations/{generation_id}
    3. Handle terminal states (COMPLETED, FAILED, ERRORED)
    4. Fetch final results from GET /api/proxy/v2/generations/{generation_id}/result

    Subclasses must implement:
    - _build_payload(): Build the request payload for generation submission
    - _parse_result(): Parse the model-specific result data
    - _set_safe_defaults(): Clear output parameters on error

    This base class handles all polling logic, API error handling, and status management.
    """

    SERVICE_NAME = "Griptape"
    API_KEY_NAME = "GT_CLOUD_API_KEY"

    # Polling configuration
    DEFAULT_POLL_INTERVAL = 5
    DEFAULT_MAX_ATTEMPTS = 120  # 10 minutes with 5s intervals

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)

        # Compute API base once
        base = os.getenv("GT_CLOUD_BASE_URL", "https://cloud.griptape.ai")
        base_slash = base if base.endswith("/") else base + "/"
        api_base = urljoin(base_slash, "api/")
        self._proxy_base = urljoin(api_base, "proxy/v2/")

    @abstractmethod
    async def _build_payload(self) -> dict[str, Any]:
        """Build the request payload for generation submission.

        This method must be implemented by subclasses to build the model-specific
        payload that will be sent to POST /api/proxy/v2/models/{model_id}.

        This method is async to support operations like image downloading/encoding.

        Returns:
            dict: The request payload to send to the API
        """

    @abstractmethod
    async def _parse_result(self, result_json: dict[str, Any], generation_id: str) -> None:
        """Parse the model-specific result data and set output parameters.

        This method must be implemented by subclasses to parse the result data
        from GET /api/proxy/v2/generations/{generation_id}/result and set the
        appropriate output parameters.

        Args:
            result_json: The JSON response from the /result endpoint
            generation_id: The generation ID for this request
        """

    @abstractmethod
    def _set_safe_defaults(self) -> None:
        """Clear all output parameters on error.

        This method must be implemented by subclasses to reset all output
        parameters to safe default values when an error occurs.
        """

    def _extract_error_message(self, response_json: dict[str, Any]) -> str:
        """Extract error message from failed/errored generation response.

        Default implementation follows this hierarchy:
        1. status_detail.details (user-oriented message)
        2. entire status_detail object
        3. top-level error field
        4. full response

        Subclasses can override this to add model-specific error extraction logic.

        Args:
            response_json: The JSON response from the generation status endpoint
                          when status is FAILED or ERRORED

        Returns:
            str: A formatted error message to display to the user
        """
        if not response_json:
            return f"{self.name} generation failed with no error details provided by API."

        # First, try to extract from status_detail.details (user-oriented message)
        status_detail = response_json.get("status_detail")
        if status_detail and isinstance(status_detail, dict):
            details = status_detail.get("details")
            if details:
                return f"{self.name} {details}"

        # Try top-level error field
        error = response_json.get("error")
        if error:
            if isinstance(error, dict):
                error_msg = error.get("message") or error.get("error") or str(error)
                return f"{self.name} {error_msg}"
            return f"{self.name} {error}"

        # Try entire status_detail object
        if status_detail:
            return f"{self.name} generation failed.\n\nError details:\n{status_detail}"

        # Final fallback: show the full response
        return f"{self.name} generation failed.\n\nFull API response:\n{response_json}"

    def _get_api_model_id(self) -> str:
        """Get the API model ID for this generation.

        Subclasses can override this if they need to map friendly names to API IDs.
        By default, returns the value of the 'model' parameter if it exists.

        Returns:
            str: The model ID to use in the API request
        """
        return self.get_parameter_value("model") or ""

    def _validate_api_key(self) -> str:
        """Validate and return the API key.

        Returns:
            str: The API key

        Raises:
            ValueError: If API key is missing
        """
        api_key = GriptapeNodes.SecretsManager().get_secret(self.API_KEY_NAME)
        if not api_key:
            self._set_safe_defaults()
            msg = f"{self.name} is missing {self.API_KEY_NAME}. Ensure it's set in the environment/config."
            raise ValueError(msg)
        return api_key

    def _log(self, message: str) -> None:
        """Log a message with error suppression."""
        with suppress(Exception):
            logger.info(message)

    async def _submit_generation(
        self, payload: dict[str, Any], headers: dict[str, str], api_model_id: str
    ) -> str | None:
        """Submit generation request to the v2 API.

        Args:
            payload: The request payload
            headers: HTTP headers including Authorization
            api_model_id: The model ID to use in the URL

        Returns:
            str | None: The generation ID if successful, None otherwise

        Raises:
            RuntimeError: If the API request fails
        """
        proxy_url = urljoin(self._proxy_base, f"models/{api_model_id}")
        self._log(f"Submitting generation request to {proxy_url}")

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(proxy_url, json=payload, headers=headers, timeout=60)
                response.raise_for_status()
                response_json = response.json()
                self._log("Request submitted successfully")
        except httpx.HTTPStatusError as e:
            self._log(f"HTTP error: {e.response.status_code} - {e.response.text}")
            error_msg = self._extract_http_error_message(e.response)
            raise RuntimeError(error_msg) from e
        except Exception as e:
            self._log(f"Request failed: {e}")
            msg = f"{self.name} request failed: {e}"
            raise RuntimeError(msg) from e

        generation_id = response_json.get("generation_id")
        if generation_id:
            self._log(f"Submitted. generation_id={generation_id}")
            return str(generation_id)

        self._log("No generation_id returned from POST response")
        return None

    def _extract_http_error_message(self, response: httpx.Response) -> str:
        """Extract error message from HTTP error response.

        Args:
            response: The HTTP response object

        Returns:
            str: Formatted error message
        """
        try:
            error_json = response.json()
        except Exception:
            return f"{self.name}: API error: {response.status_code} - {response.text}"
        else:
            error_message = self._extract_error_message(error_json)
            return f"{self.name}: {error_message}"

    async def _poll_generation_status(self, generation_id: str, headers: dict[str, str]) -> dict[str, Any] | None:
        """Poll generation status until terminal state is reached.

        Args:
            generation_id: The generation ID to poll
            headers: HTTP headers including Authorization

        Returns:
            dict | None: The final status response, or None if polling failed
        """
        get_url = urljoin(self._proxy_base, f"generations/{generation_id}")
        max_attempts = self.DEFAULT_MAX_ATTEMPTS
        poll_interval = self.DEFAULT_POLL_INTERVAL

        async with httpx.AsyncClient() as client:
            for attempt in range(max_attempts):
                try:
                    self._log(f"[GriptapeProxyNode] Polling attempt #{attempt + 1} for generation {generation_id}")

                    response = await client.get(get_url, headers=headers, timeout=60)
                    response.raise_for_status()
                    result_json = response.json()

                    status = result_json.get("status", "unknown")
                    self._log(f"Status: {status}")

                    if status == "COMPLETED":
                        return result_json

                    if status in ["FAILED", "ERRORED"]:
                        logger.error("%s: Generation failed with status: %s", self.name, status)
                        logger.error("%s: Error response: %s", self.name, result_json)
                        self._set_safe_defaults()
                        error_message = self._extract_error_message(result_json)
                        logger.error("%s: Extracted error message: %s", self.name, error_message)
                        if not error_message:
                            error_message = f"{self.name} generation failed with status {status} but no error details were provided."
                        self._set_status_results(was_successful=False, result_details=error_message)
                        return None

                    # Still processing (QUEUED or RUNNING), wait before next poll
                    if attempt < max_attempts - 1:
                        await asyncio.sleep(poll_interval)

                except httpx.HTTPStatusError as e:
                    self._log(f"HTTP error while polling: {e.response.status_code} - {e.response.text}")
                    if attempt == max_attempts - 1:
                        self._set_safe_defaults()
                        error_msg = f"Failed to poll generation status: HTTP {e.response.status_code}"
                        self._set_status_results(was_successful=False, result_details=error_msg)
                        return None
                except Exception as e:
                    self._log(f"Error while polling: {e}")
                    if attempt == max_attempts - 1:
                        self._set_safe_defaults()
                        error_msg = f"Failed to poll generation status: {e}"
                        self._set_status_results(was_successful=False, result_details=error_msg)
                        return None

        # Timeout reached
        self._log("Polling timed out waiting for result")
        self._set_safe_defaults()
        self._set_status_results(
            was_successful=False,
            result_details=f"Generation timed out after {max_attempts * poll_interval} seconds waiting for result.",
        )
        return None

    async def _fetch_generation_result(
        self, generation_id: str, headers: dict[str, str], client: httpx.AsyncClient
    ) -> dict[str, Any] | None:
        """Fetch the final result from the /result endpoint.

        Args:
            generation_id: The generation ID
            headers: HTTP headers including Authorization
            client: The HTTP client to use

        Returns:
            dict | None: The result JSON or dict containing raw bytes, or None if fetch failed
        """
        result_url = urljoin(self._proxy_base, f"generations/{generation_id}/result")
        self._log(f"Fetching result from {result_url}")

        try:
            response = await client.get(result_url, headers=headers, timeout=300)
            response.raise_for_status()
        except httpx.HTTPStatusError as e:
            self._log(f"HTTP error fetching result: {e.response.status_code} - {e.response.text}")
            self._set_safe_defaults()
            error_msg = f"Failed to fetch generation result: HTTP {e.response.status_code}"
            self._set_status_results(was_successful=False, result_details=error_msg)
            return None
        except Exception as e:
            self._log(f"Error fetching result: {e}")
            self._set_safe_defaults()
            error_msg = f"Failed to fetch generation result: {e}"
            self._set_status_results(was_successful=False, result_details=error_msg)
            return None
        else:
            # Check Content-Type to determine if response is JSON or binary
            content_type = response.headers.get("content-type", "").lower()

            if "application/json" in content_type:
                result_json = response.json()
                self._log("Result fetched successfully (JSON)")
                return result_json

            # Handle binary responses (raw audio, video, etc.)
            self._log(f"Result fetched successfully (binary, content-type: {content_type})")
            return {"raw_bytes": response.content}

    def _handle_api_key_validation_error(self, e: ValueError) -> None:
        """Handle API key validation errors."""
        self._set_safe_defaults()
        self._set_status_results(was_successful=False, result_details=str(e))
        self._handle_failure_exception(e)

    def _handle_payload_build_error(self, e: Exception) -> None:
        """Handle payload building errors."""
        self._set_safe_defaults()
        error_msg = f"{self.name}: Failed to build request payload: {e}"
        self._set_status_results(was_successful=False, result_details=error_msg)
        self._handle_failure_exception(e)

    def _handle_missing_model_id(self) -> None:
        """Handle missing model ID error."""
        self._set_safe_defaults()
        error_msg = f"{self.name}: No model ID provided"
        self._set_status_results(was_successful=False, result_details=error_msg)

    def _handle_submission_error(self, e: RuntimeError) -> None:
        """Handle generation submission errors."""
        self._set_safe_defaults()
        self._set_status_results(was_successful=False, result_details=str(e))
        self._handle_failure_exception(e)

    def _handle_result_parsing_error(self, e: Exception) -> None:
        """Handle result parsing errors."""
        self._log(f"Error parsing result: {e}")
        self._set_safe_defaults()
        error_msg = f"Failed to parse generation result: {e}"
        self._set_status_results(was_successful=False, result_details=error_msg)
        self._handle_failure_exception(e)

    async def _submit_and_poll(self, headers: dict[str, str]) -> tuple[str, dict[str, Any]] | None:
        """Submit generation request and poll for completion.

        Args:
            headers: HTTP headers including Authorization

        Returns:
            tuple | None: (generation_id, status_response) if successful, None otherwise
        """
        # Build payload
        try:
            payload = await self._build_payload()
        except Exception as e:
            self._handle_payload_build_error(e)
            return None

        # Get API model ID
        api_model_id = self._get_api_model_id()
        if not api_model_id:
            self._handle_missing_model_id()
            return None

        # Submit request to get generation ID
        try:
            generation_id = await self._submit_generation(payload, headers, api_model_id)
            if not generation_id:
                self._set_safe_defaults()
                self._set_status_results(
                    was_successful=False,
                    result_details="No generation_id returned from API. Cannot proceed with generation.",
                )
                return None
        except RuntimeError as e:
            self._handle_submission_error(e)
            return None

        # Store generation_id if output parameter exists
        if "generation_id" in self.parameter_output_values:
            self.parameter_output_values["generation_id"] = generation_id

        # Poll for completion
        status_response = await self._poll_generation_status(generation_id, headers)
        if not status_response:
            return None

        return generation_id, status_response

    async def _process_generation(self) -> None:
        """Main processing logic that orchestrates the generation flow.

        This method handles:
        1. API key validation
        2. Payload building
        3. Generation submission
        4. Status polling
        5. Result fetching and parsing
        """
        # Clear execution status at the start
        self._clear_execution_status()

        # Validate API key
        try:
            api_key = self._validate_api_key()
        except ValueError as e:
            self._handle_api_key_validation_error(e)
            return

        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

        # Submit and poll
        result = await self._submit_and_poll(headers)
        if not result:
            return

        generation_id, _status_response = result

        # Fetch and parse result
        async with httpx.AsyncClient() as client:
            result_json = await self._fetch_generation_result(generation_id, headers, client)
            if not result_json:
                return

            # Store provider_response if output parameter exists
            if "provider_response" in self.parameter_output_values:
                self.parameter_output_values["provider_response"] = result_json

            # Parse model-specific result
            try:
                await self._parse_result(result_json, generation_id)
            except Exception as e:
                self._handle_result_parsing_error(e)

    async def aprocess(self) -> None:
        """Async processing entry point."""
        await self._process_generation()

    @staticmethod
    async def _download_bytes_from_url(url: str) -> bytes | None:
        """Download bytes from a URL.

        Args:
            url: The URL to download from

        Returns:
            bytes | None: The downloaded bytes, or None if download failed
        """
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(url, timeout=120)
                resp.raise_for_status()
                return resp.content
        except Exception:
            return None
