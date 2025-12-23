from __future__ import annotations

import base64
import logging
from typing import Any

import httpx
from griptape.artifacts.video_url_artifact import VideoUrlArtifact

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
from griptape_nodes.traits.options import Options
from griptape_nodes_library.griptape_proxy_node import GriptapeProxyNode

logger = logging.getLogger("griptape_nodes")

__all__ = ["SeedanceVideoGeneration"]


class SeedanceVideoGeneration(GriptapeProxyNode):
    """Generate a video using the Seedance model via Griptape Cloud model proxy.

    Inputs:
        - prompt (str): Text prompt for the video (supports provider flags like --resolution)
        - model_id (str): Provider model id (default: seedance-1-0-pro-250528)
        - resolution (str): Output resolution (default: 1080p, options: 480p, 720p, 1080p)
        - ratio (str): Output aspect ratio (default: 16:9, options: 16:9, 4:3, 1:1, 3:4, 9:16, 21:9)
        - duration (int): Video duration in seconds (default: 5, options: 5, 10)
        - camerafixed (bool): Camera fixed flag (default: False)
        - first_frame (ImageArtifact|ImageUrlArtifact|str): Optional first frame image (URL or base64 data URI)
        - last_frame (ImageArtifact|ImageUrlArtifact|str): Optional last frame image for i2v model (URL or base64 data URI)

    Outputs:
        - generation_id (str): Griptape Cloud generation id
        - provider_response (dict): Verbatim response from API (initial POST)
        - video_url (VideoUrlArtifact): Saved static video URL
        - was_successful (bool): Whether the generation succeeded
        - result_details (str): Details about the generation result or error
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.category = "API Nodes"
        self.description = "Generate video via Seedance through Griptape Cloud model proxy"

        # INPUTS / PROPERTIES
        self.add_parameter(
            Parameter(
                name="prompt",
                input_types=["str"],
                type="str",
                tooltip="Text prompt for the video (supports provider flags)",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={
                    "multiline": True,
                    "placeholder_text": "Describe the video...",
                    "display_name": "Prompt",
                },
            )
        )

        self.add_parameter(
            Parameter(
                name="model_id",
                input_types=["str"],
                type="str",
                default_value="seedance-1-0-pro-250528",
                tooltip="Model id to call via proxy",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={
                    "display_name": "Model ID",
                    "hide": False,
                },
                traits={
                    Options(
                        choices=[
                            "seedance-1-0-pro-250528",
                            "seedance-1-0-pro-fast-251015",
                            "seedance-1-0-lite-t2v-250428",
                            "seedance-1-0-lite-i2v-250428",
                        ]
                    )
                },
            )
        )

        # Resolution selection
        self.add_parameter(
            Parameter(
                name="resolution",
                input_types=["str"],
                type="str",
                default_value="1080p",
                tooltip="Output resolution",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                traits={Options(choices=["480p", "720p", "1080p"])},
            )
        )

        # Aspect ratio selection
        self.add_parameter(
            Parameter(
                name="ratio",
                input_types=["str"],
                type="str",
                default_value="16:9",
                tooltip="Output aspect ratio",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                traits={Options(choices=["16:9", "4:3", "1:1", "3:4", "9:16", "21:9"])},
            )
        )

        # Duration in seconds
        self.add_parameter(
            Parameter(
                name="duration",
                input_types=["int"],
                type="int",
                default_value=5,
                tooltip="Video duration in seconds",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                traits={Options(choices=[5, 10])},
            )
        )

        # Camera fixed flag
        self.add_parameter(
            Parameter(
                name="camerafixed",
                input_types=["bool"],
                type="bool",
                default_value=False,
                tooltip="Camera fixed",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
            )
        )

        # Optional first frame (image) - accepts artifact or URL/base64 string
        self.add_parameter(
            Parameter(
                name="first_frame",
                input_types=["ImageArtifact", "ImageUrlArtifact", "str"],
                type="ImageArtifact",
                default_value=None,
                tooltip="Optional first frame image (URL or base64 data URI)",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={"display_name": "First Frame"},
            )
        )

        # Optional last frame (image) - accepts artifact or URL/base64 string valid only with seedance-1-0-lite-i2v
        self.add_parameter(
            Parameter(
                name="last_frame",
                input_types=["ImageArtifact", "ImageUrlArtifact", "str"],
                type="ImageArtifact",
                default_value=None,
                tooltip="Optional Last frame image for seedance-1-0-lite-i2v model(URL or base64 data URI)",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={"display_name": "Last Frame"},
            )
        )

        # OUTPUTS
        self.add_parameter(
            Parameter(
                name="generation_id",
                output_type="str",
                tooltip="Griptape Cloud generation id",
                allowed_modes={ParameterMode.OUTPUT},
            )
        )

        self.add_parameter(
            Parameter(
                name="provider_response",
                output_type="dict",
                type="dict",
                tooltip="Verbatim response from API (initial POST)",
                allowed_modes={ParameterMode.OUTPUT},
                ui_options={"hide_property": True},
            )
        )

        self.add_parameter(
            Parameter(
                name="video_url",
                output_type="VideoUrlArtifact",
                type="VideoUrlArtifact",
                tooltip="Saved video as URL artifact for downstream display",
                allowed_modes={ParameterMode.OUTPUT, ParameterMode.PROPERTY},
                settable=False,
                ui_options={"is_full_width": True, "pulse_on_run": True},
            )
        )

        # Create status parameters for success/failure tracking (at the end)
        self._create_status_parameters(
            result_details_tooltip="Details about the video generation result or any errors",
            result_details_placeholder="Generation status and details will appear here.",
            parameter_group_initially_collapsed=False,
        )

    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        """Handle parameter value changes to show/hide dependent parameters."""
        if parameter.name == "model_id":
            # Show last_frame parameter only for i2v model
            show_last_frame = value == "seedance-1-0-lite-i2v-250428"
            if show_last_frame:
                self.show_parameter_by_name("last_frame")
            else:
                self.hide_parameter_by_name("last_frame")

        return super().after_value_set(parameter, value)

    def _get_api_model_id(self) -> str:
        """Get the API model ID for this generation."""
        return self.get_parameter_value("model_id") or "seedance-1-0-pro-250528"

    async def _build_payload(self) -> dict[str, Any]:
        """Build the request payload for Seedance generation."""
        params = {
            "prompt": self.get_parameter_value("prompt") or "",
            "model_id": self._get_api_model_id(),
            "resolution": self.get_parameter_value("resolution") or "1080p",
            "ratio": self.get_parameter_value("ratio") or "16:9",
            "first_frame": self.get_parameter_value("first_frame"),
            "last_frame": self.get_parameter_value("last_frame"),
            "duration": self.get_parameter_value("duration"),
            "camerafixed": self.get_parameter_value("camerafixed"),
        }

        # Build text payload with flags
        text_parts = [params["prompt"].strip()]
        if params["resolution"]:
            text_parts.append(f"--resolution {params['resolution']}")
        if params["ratio"]:
            text_parts.append(f"--ratio {params['ratio']}")
        if params["duration"] is not None and str(params["duration"]).strip():
            text_parts.append(f"--duration {str(int(params['duration'])).strip()}")
        if params["camerafixed"] is not None:
            cam_str = "true" if bool(params["camerafixed"]) else "false"
            text_parts.append(f"--camerafixed {cam_str}")

        text_payload = "  ".join([p for p in text_parts if p])
        content_list: list[dict[str, Any]] = [{"type": "text", "text": text_payload}]

        # Add frame images based on model capabilities
        await self._add_frame_images(content_list, params)

        return {"model": params["model_id"], "content": content_list}

    async def _parse_result(self, result_json: dict[str, Any], generation_id: str) -> None:
        """Parse Seedance result and save generated video."""
        # Extract video URL from result
        extracted_url = self._extract_video_url(result_json)
        if not extracted_url:
            self.parameter_output_values["video_url"] = None
            self._set_status_results(
                was_successful=False,
                result_details="Generation completed but no video URL was found in the response.",
            )
            return

        # Download and save the video
        try:
            logger.info("Downloading video from URL")
            video_bytes = await self._download_bytes_from_url(extracted_url)
        except Exception as e:
            logger.error("Failed to download video: %s", e)
            video_bytes = None

        if video_bytes:
            try:
                filename = f"seedance_video_{generation_id}.mp4"
                static_files_manager = GriptapeNodes.StaticFilesManager()
                saved_url = static_files_manager.save_static_file(video_bytes, filename)
                self.parameter_output_values["video_url"] = VideoUrlArtifact(value=saved_url, name=filename)
                logger.info("Saved video to static storage as %s", filename)
                self._set_status_results(
                    was_successful=True, result_details=f"Video generated successfully and saved as {filename}."
                )
            except Exception as e:
                logger.error("Failed to save video: %s", e)
                self.parameter_output_values["video_url"] = VideoUrlArtifact(value=extracted_url)
                self._set_status_results(
                    was_successful=True,
                    result_details=f"Video generated successfully. Using provider URL (could not save to static storage: {e}).",
                )
        else:
            self.parameter_output_values["video_url"] = VideoUrlArtifact(value=extracted_url)
            self._set_status_results(
                was_successful=True,
                result_details="Video generated successfully. Using provider URL (could not download video bytes).",
            )

    def _set_safe_defaults(self) -> None:
        """Set safe default values for outputs."""
        self.parameter_output_values["generation_id"] = ""
        self.parameter_output_values["provider_response"] = None
        self.parameter_output_values["video_url"] = None

    async def _add_frame_images(self, content_list: list[dict[str, Any]], params: dict[str, Any]) -> None:
        """Add frame images to content list based on model capabilities."""
        model_id = params["model_id"]

        if model_id == "seedance-1-0-pro-250528":
            await self._add_first_frame_only(content_list, params)
        elif model_id == "seedance-1-0-lite-i2v-250428":
            await self._add_i2v_frames(content_list, params)
        # Add other model handling here as needed

    async def _add_first_frame_only(self, content_list: list[dict[str, Any]], params: dict[str, Any]) -> None:
        """Add first frame for models that only support single frame input."""
        frame_url = await self._prepare_frame_url(params["first_frame"])
        if frame_url:
            content_list.append({"type": "image_url", "image_url": {"url": frame_url}})

    async def _add_i2v_frames(self, content_list: list[dict[str, Any]], params: dict[str, Any]) -> None:
        """Add frames for image-to-video models that support first and last frames."""
        has_last_frame = params["last_frame"] is not None

        # Add first frame
        first_frame_url = await self._prepare_frame_url(params["first_frame"])
        if first_frame_url:
            if has_last_frame:
                # When both frames present, add role identifiers
                content_list.append({"type": "image_url", "image_url": {"url": first_frame_url}, "role": "first_frame"})
            else:
                # When only first frame, no role needed
                content_list.append({"type": "image_url", "image_url": {"url": first_frame_url}})

        # Add last frame if provided
        if has_last_frame:
            last_frame_url = await self._prepare_frame_url(params["last_frame"])
            if last_frame_url:
                content_list.append({"type": "image_url", "image_url": {"url": last_frame_url}, "role": "last_frame"})

    async def _prepare_frame_url(self, frame_input: Any) -> str | None:
        """Convert frame input to a usable URL, handling inlining of external URLs."""
        if not frame_input:
            return None

        frame_url = self._coerce_image_url_or_data_uri(frame_input)
        if not frame_url:
            return None
        return await self._inline_external_url(frame_url)

    async def _inline_external_url(self, url: str) -> str | None:
        """Inline external URLs as base64 data URIs."""
        if not isinstance(url, str) or not url.startswith(("http://", "https://")):
            return url

        try:
            async with httpx.AsyncClient() as client:
                rff = await client.get(url, timeout=20)
                rff.raise_for_status()
                ct = (rff.headers.get("content-type") or "image/jpeg").split(";")[0]
                if not ct.startswith("image/"):
                    ct = "image/jpeg"
                b64 = base64.b64encode(rff.content).decode("utf-8")
                logger.debug("Frame URL converted to data URI for proxy")
                return f"data:{ct};base64,{b64}"
        except Exception as e:
            logger.warning("Failed to inline frame URL: %s", e)
            return url

    @staticmethod
    def _coerce_image_url_or_data_uri(val: Any) -> str | None:
        """Coerce image input to URL or data URI."""
        if val is None:
            return None

        # String handling
        if isinstance(val, str):
            v = val.strip()
            if not v:
                return None
            return v if v.startswith(("http://", "https://", "data:image/")) else f"data:image/png;base64,{v}"

        # Artifact-like objects
        try:
            # ImageUrlArtifact: .value holds URL string
            v = getattr(val, "value", None)
            if isinstance(v, str) and v.startswith(("http://", "https://", "data:image/")):
                return v
            # ImageArtifact: .base64 holds raw or data-URI
            b64 = getattr(val, "base64", None)
            if isinstance(b64, str) and b64:
                return b64 if b64.startswith("data:image/") else f"data:image/png;base64,{b64}"
        except Exception:  # noqa: S110
            pass

        return None

    @staticmethod
    def _extract_video_url(obj: dict[str, Any] | None) -> str | None:
        """Extract video URL from Seedance response."""
        if not obj:
            return None
        # Heuristic search for a URL in common places
        # 1) direct fields
        for key in ("url", "video_url", "output_url"):
            val = obj.get(key) if isinstance(obj, dict) else None
            if isinstance(val, str) and val.startswith("http"):
                return val
        # 2) nested known containers (Seedance returns content.video_url)
        for key in ("result", "data", "output", "outputs", "content", "task_result"):
            nested = obj.get(key) if isinstance(obj, dict) else None
            if isinstance(nested, dict):
                url = SeedanceVideoGeneration._extract_video_url(nested)
                if url:
                    return url
            elif isinstance(nested, list):
                for item in nested:
                    url = SeedanceVideoGeneration._extract_video_url(item if isinstance(item, dict) else None)
                    if url:
                        return url
        return None
