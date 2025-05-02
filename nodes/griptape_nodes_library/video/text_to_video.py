import time
import jwt
import requests
from griptape_nodes.retained_mode.griptape_nodes import logger
from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import AsyncResult, ControlNode
from griptape.artifacts import TextArtifact

ACCESS_KEY = "40e7a4bb24244e999e02b882650bd7d3"
SECRET_KEY = "3ad48f8845f54e279f2bc4937f3750e3"
BASE_URL = "https://api.klingai.com/v1/videos/text2video"


def encode_jwt_token(ak, sk):
    headers = {
        "alg": "HS256",
        "typ": "JWT"
    }

    payload = {
        "iss": ak,
        "exp": int(time.time()) + 1800,  # valid for 30 minutes
        "nbf": int(time.time()) - 5      # valid 5 seconds ago
    }

    token = jwt.encode(payload, sk, algorithm="HS256", headers=headers)
    return token


class TextToVideo(ControlNode):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)

        self.add_parameter(
            Parameter(
                name="prompt",
                input_types=["str"],
                output_type="str",
                type="str",
                tooltip="Text prompt for video generation",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={"multiline": True, "placeholder_text": "Describe the video you want..."},
            )
        )
        self.add_parameter(
            Parameter(
                name="video_url",
                type="str",
                output_type="str",
                default_value="",
                allowed_modes={ParameterMode.OUTPUT},
                tooltip="Video URL",
            )
        )

    def process(self) -> AsyncResult:
        prompt = self.get_parameter_value("prompt")

        def generate_video():
            jwt_token = encode_jwt_token(ACCESS_KEY, SECRET_KEY)

            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {jwt_token}"
            }

            payload = {
                "model_name": "kling-v1",
                "prompt": prompt,
                "duration": "5"
            }

            response = requests.post(BASE_URL, headers=headers, json=payload)
            response.raise_for_status()
            task_id = response.json()["data"]["task_id"]

            poll_url = f"{BASE_URL}/{task_id}"
            video_url = None

            while True:
                time.sleep(3)
                result = requests.get(poll_url, headers=headers).json()
                status = result["data"]["task_status"]
                logger.info(f"Video generation status: {status}")
                if status == "succeed":
                    logger.info(f"Video generation succeeded: {result['data']['task_result']['videos'][0]['url']}")
                    video_url = result["data"]["task_result"]["videos"][0]["url"]
                    break
                elif status == "failed":
                    logger.error(f"Video generation failed: {result['data']['task_status_msg']}")
                    raise RuntimeError(f"Video generation failed: {result['data']['task_status_msg']}")

            self.publish_update_to_parameter("video_url", video_url)
            logger.info(f"Video URL: {video_url}")
            return TextArtifact(video_url)

        yield generate_video
