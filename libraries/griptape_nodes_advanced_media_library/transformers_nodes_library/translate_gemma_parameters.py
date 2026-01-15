import logging
from typing import Any

import torch  # type: ignore[reportMissingImports]
from transformers import pipeline  # type: ignore[reportMissingImports]

from griptape_nodes.exe_types.node_types import BaseNode
from griptape_nodes.exe_types.param_components.huggingface.huggingface_repo_parameter import HuggingFaceRepoParameter
from griptape_nodes.exe_types.param_components.log_parameter import LogParameter

logger = logging.getLogger("transformers_nodes_library")

# Default language constants
DEFAULT_SOURCE_LANG = "English (en)"
DEFAULT_TARGET_LANG = "Spanish (es)"
CUSTOM_LANG_OPTION = "Custom..."

# Map display names to ISO language codes (alphabetically sorted)
LANGUAGE_CODE_MAP = {
    "Arabic (ar)": "ar",
    "Chinese (zh)": "zh",
    "Czech (cs)": "cs",
    "Danish (da)": "da",
    "Dutch (nl)": "nl",
    DEFAULT_SOURCE_LANG: "en",
    "Finnish (fi)": "fi",
    "French (fr)": "fr",
    "German (de)": "de",
    "Hebrew (he)": "he",
    "Hindi (hi)": "hi",
    "Indonesian (id)": "id",
    "Italian (it)": "it",
    "Japanese (ja)": "ja",
    "Korean (ko)": "ko",
    "Norwegian (no)": "no",
    "Polish (pl)": "pl",
    "Portuguese (pt)": "pt",
    "Russian (ru)": "ru",
    DEFAULT_TARGET_LANG: "es",
    "Swedish (sv)": "sv",
    "Thai (th)": "th",
    "Turkish (tr)": "tr",
    "Ukrainian (uk)": "uk",
    "Vietnamese (vi)": "vi",
}

# Language choices for dropdown (derived from map + Custom option)
LANGUAGE_CHOICES = [*LANGUAGE_CODE_MAP.keys(), CUSTOM_LANG_OPTION]


class TranslateGemmaParameters:
    def __init__(self, node: BaseNode):
        self._node = node
        self._huggingface_repo_parameter = HuggingFaceRepoParameter(
            node,
            repo_ids=[
                "google/translategemma-4b-it",
                "google/translategemma-12b-it",
                "google/translategemma-27b-it",
            ],
        )
        self._log_parameter = LogParameter(node)
        self._pipeline: Any = None

    def add_input_parameters(self) -> None:
        self._huggingface_repo_parameter.add_input_parameters()

    def add_logs_output_parameter(self) -> None:
        self._log_parameter.add_output_parameters()

    def get_repo_revision(self) -> tuple[str, str]:
        return self._huggingface_repo_parameter.get_repo_revision()

    def load_pipeline(self) -> Any:
        repo_id, revision = self.get_repo_revision()

        # Determine device
        if torch.cuda.is_available():
            device = "cuda"
        else:
            device = "cpu"
            logger.warning("CUDA not available, falling back to CPU. Translation will be slow.")

        # Load pipeline
        self._pipeline = pipeline(
            "image-text-to-text",
            model=repo_id,
            revision=revision,
            device=device,
            torch_dtype=torch.bfloat16,
        )

        return self._pipeline

    def translate_text(
        self,
        pipe: Any,
        input_text: str,
        source_lang_code: str,
        target_lang_code: str,
        max_new_tokens: int,
    ) -> str:
        # Format message for translation
        messages = [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "source_lang_code": source_lang_code,
                        "target_lang_code": target_lang_code,
                        "text": input_text,
                    }
                ],
            }
        ]

        # Execute translation
        output = pipe(text=messages, max_new_tokens=max_new_tokens)
        translated_text = output[0]["generated_text"][-1]["content"]

        return translated_text

    def validate_before_node_run(self) -> list[Exception] | None:
        return self._huggingface_repo_parameter.validate_before_node_run()

    def append_stdout_to_logs(self):
        return self._log_parameter.append_stdout_to_logs()

    def append_to_logs(self, text: str) -> None:
        self._log_parameter.append_to_logs(text)

    @staticmethod
    def get_language_code(preset_value: str, custom_value: str) -> str:
        """Resolve language code from preset dropdown value or custom input."""
        if preset_value == CUSTOM_LANG_OPTION:
            return custom_value
        return LANGUAGE_CODE_MAP.get(preset_value, "en")
