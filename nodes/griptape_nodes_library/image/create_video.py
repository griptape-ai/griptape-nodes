import uuid
import time
import jwt
import requests

from griptape.artifacts import UrlArtifact
from griptape.structures.agent import Agent

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import AsyncResult, BaseNode, ControlNode
from griptape_nodes.exe_types.node_types import AsyncResult
from griptape_nodes.retained_mode.griptape_nodes import logger
from griptape_nodes_library.utils.error_utils import try_throw_error

# Configuration constants
ACCESS_KEY_ENV_VAR = "KLING_AI_ACCESS_KEY"
SECRET_KEY_ENV_VAR = "KLING_AI_SECRET_KEY"
SERVICE = "KlingAI"
DEFAULT_MODEL = "klingv1"
POLLING_INTERVAL = 2
MAX_POLL_ATTEMPTS = 90  # 1 minute total polling
JWT_EXPIRATION_SECONDS = 1800  # 30 minutes
JWT_NBF_OFFSET_SECONDS = 5  # 5 seconds before now
DEFAULT_BASE_URL = "https://api.klingai.com"


class KlingVideoGenerationBaseTask:
    def __init__(
        self,
        image_url: str,
        access_key: str,
        secret_key: str,
        motion_intensity: str = "medium",
        stitch_back: bool = False,
        model: str = DEFAULT_MODEL,
        base_url: str = DEFAULT_BASE_URL
    ):
        self.image_url = image_url
        self.access_key = access_key
        self.secret_key = secret_key
        self.motion_intensity = motion_intensity
        self.stitch_back = stitch_back
        self.model = model
        self.base_url = base_url

    def _encode_jwt_token(self) -> str:
        """Generates the JWT token for API authentication."""
        headers = {
            "alg": "HS256",
            "typ": "JWT"
        }
        payload = {
            "iss": self.access_key,
            "exp": int(time.time()) + JWT_EXPIRATION_SECONDS,
            "nbf": int(time.time()) - JWT_NBF_OFFSET_SECONDS
        }
        try:
            token = jwt.encode(payload, self.secret_key, headers=headers)
            return token
        except Exception as e:
            raise RuntimeError(f"Failed to encode JWT token: {e}") from e

    def _poll_for_completion(self, video_id: str) -> str:
        """Poll Kling AI API until the video is ready and return its URL"""
        status_url = f"{self.base_url}/v1/videos/{video_id}"
        
        for attempt in range(MAX_POLL_ATTEMPTS):
            try:
                # Generate fresh token for each poll attempt
                token = self._encode_jwt_token()
                headers = {
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                }

                response = requests.get(status_url, headers=headers)
                response.raise_for_status()
                result = response.json()

                if result.get("code") != 0:
                    msg = result.get("message", "Unknown API error during polling")
                    raise RuntimeError(f"Kling API Error (code {result.get('code')}): {msg}")

                status_data = result.get("data", {})
                status = status_data.get("status")

                if status == "completed":
                    return status_data.get("url")
                elif status == "failed":
                    status_msg = status_data.get("error", "Unknown failure reason")
                    raise RuntimeError(f"Kling task failed: {status_msg}")
                elif status in ["submitted", "processing"]:
                    time.sleep(POLLING_INTERVAL)
                    continue
                else:
                    raise RuntimeError(f"Unknown Kling task status: {status}")

            except requests.exceptions.RequestException as e:
                raise RuntimeError(f"Failed to query Kling task status: {e}")
            except Exception as e:
                raise RuntimeError(f"Error processing Kling poll response: {e}")

        raise RuntimeError(f"Kling task did not complete after {MAX_POLL_ATTEMPTS * POLLING_INTERVAL} seconds.")

    def execute(self) -> str:
        try:
            # Generate JWT token
            token = self._encode_jwt_token()
            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            }

            # Build payload according to API documentation
            data = {
                "image_url": self.image_url,
                "model": self.model,
                "motion_intensity": self.motion_intensity,
                "stitch_back": self.stitch_back
            }

            # Make the initial POST request
            create_url = f"{self.base_url}/v1/image-to-video"
            response = requests.post(create_url, headers=headers, json=data)
            response.raise_for_status()
            result = response.json()

            if result.get("code") != 0:
                msg = result.get("message", "Unknown API error")
                raise RuntimeError(f"Kling API Error (code {result.get('code')}): {msg}")

            task_data = result.get("data", {})
            video_id = task_data.get("id")
            if not video_id:
                raise ValueError("Kling API did not return a video ID.")

            # Poll for completion
            return self._poll_for_completion(video_id)

        except requests.exceptions.RequestException as e:
            raise RuntimeError(f"Kling API request failed: {e} - Response: {e.response.text if e.response else 'N/A'}")
        except Exception as e:
            raise RuntimeError(f"Error in video generation: {str(e)}")


class ImageToVideo(ControlNode):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)

        self._has_connection_to_input_image = False

        self.add_parameter(
            Parameter(
                name="input_image",
                input_types=["ImageUrlArtifact", "ImageArtifact"],
                output_type="ImageUrlArtifact",
                type="ImageUrlArtifact",
                tooltip="Input image URL to convert to video",
                default_value=None,
                allowed_modes={ParameterMode.INPUT},
            )
        )
        
        # Add motion intensity parameter
        self.add_parameter(
            Parameter(
                name="motion_intensity",
                input_types=["str"],
                output_type="str",
                type="str",
                tooltip="Motion intensity: low, medium, or high",
                default_value="medium",
                allowed_modes={ParameterMode.INPUT},
            )
        )
        
        # Add stitch back parameter
        self.add_parameter(
            Parameter(
                name="stitch_back",
                input_types=["str"],
                output_type="str",
                type="str",
                tooltip="Whether to stitch the video back to the starting frame",
                default_value="false",
                allowed_modes={ParameterMode.INPUT},
            )
        )
        
        # Add model parameter
        self.add_parameter(
            Parameter(
                name="model",
                input_types=["str"],
                output_type="str",
                type="str",
                tooltip="Kling AI model to use",
                default_value=DEFAULT_MODEL,
                allowed_modes={ParameterMode.INPUT},
            )
        )
        
        self.add_parameter(
            Parameter(
                name="output_video",
                input_types=["VideoUrlArtifact", "UrlArtifact"],  # Accept both artifact types
                output_type="UrlArtifact",                       # Using UrlArtifact for compatibility
                type="UrlArtifact",
                tooltip="Output video URL",
                default_value=None,
                allowed_modes={ParameterMode.OUTPUT},
            )
        )

    def validate_node(self) -> list[Exception] | None:
        exceptions = []
        
        # Check if config values are set (note: not checking hardcoded values in your original code)
        access_key = ACCESS_KEY_ENV_VAR
        secret_key = SECRET_KEY_ENV_VAR
        
        if not access_key:
            msg = f"Missing {ACCESS_KEY_ENV_VAR} configuration"
            exceptions.append(KeyError(msg))
            
        if not secret_key:
            msg = f"Missing {SECRET_KEY_ENV_VAR} configuration"
            exceptions.append(KeyError(msg))

        # Validate that we have an input image
        input_image = self.parameter_values.get("input_image", None)
        if not input_image and not self._has_connection_to_input_image:
            msg = "No input image was provided. Cannot generate a video without an input image."
            exceptions.append(ValueError(msg))
            
        # Validate motion intensity if set
        motion_intensity = self.parameter_values.get("motion_intensity", "medium")
        if motion_intensity not in ["low", "medium", "high"]:
            msg = "Motion intensity must be one of: low, medium, high"
            exceptions.append(ValueError(msg))

        return exceptions if exceptions else None

    def process(self) -> AsyncResult:
        # Get the input parameters
        input_image = self.parameter_values.get("input_image", None)
        motion_intensity = self.parameter_values.get("motion_intensity", "medium")
        stitch_back = self.parameter_values.get("stitch_back", "false")
        model = self.parameter_values.get("model", DEFAULT_MODEL)
        
        if not input_image:
            raise ValueError("No input image provided")
            
        # Get the image URL from the artifact
        image_url = input_image.value
        
        # Get the API keys
        access_key = ACCESS_KEY_ENV_VAR
        secret_key = SECRET_KEY_ENV_VAR

        # Create and process the video generation task
        yield lambda: self._create_video_from_image(
            image_url, 
            access_key, 
            secret_key,
            motion_intensity,
            stitch_back,
            model
        )

    def after_incoming_connection(
        self,
        source_node: BaseNode,  # noqa: ARG002
        source_parameter: Parameter,  # noqa: ARG002
        target_parameter: Parameter,
    ) -> None:
        """Callback after a Connection has been established TO this Node."""
        if target_parameter.name == "input_image":
            self._has_connection_to_input_image = True

    def after_incoming_connection_removed(
        self,
        source_node: BaseNode,  # noqa: ARG002
        source_parameter: Parameter,  # noqa: ARG002
        target_parameter: Parameter,
    ) -> None:
        """Callback after a Connection TO this Node was REMOVED."""
        if target_parameter.name == "input_image":
            self._has_connection_to_input_image = False

    def _create_video_from_image(
        self, 
        image_url: str, 
        access_key: str, 
        secret_key: str,
        motion_intensity: str,
        stitch_back: str,
        model: str
    ) -> None:
        """Generate a video from an image URL and output it as a URL artifact"""
        try:
            # Create the video generation task
            task = KlingVideoGenerationBaseTask(
                image_url=image_url,
                access_key=access_key,
                secret_key=secret_key,
                motion_intensity=motion_intensity,
                stitch_back=stitch_back == "true",
                model=model
            )
            
            # Execute the task directly to get the URL
            video_url = task.execute()
            
            # Create a UrlArtifact with the URL
            url_artifact = UrlArtifact(value=video_url)
            
            # Update the output parameter with the video URL artifact
            self.publish_update_to_parameter("output_video", url_artifact)
            
        except Exception as e:
            error_message = f"Error in video generation: {str(e)}"
            logger.error(error_message)
            raise