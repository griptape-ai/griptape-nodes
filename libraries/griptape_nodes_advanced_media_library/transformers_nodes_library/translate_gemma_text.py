import logging
from typing import Any

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import AsyncResult, ControlNode
from griptape_nodes.exe_types.param_types.parameter_string import ParameterString
from griptape_nodes.traits.options import Options
from transformers_nodes_library.translate_gemma_parameters import (
    CUSTOM_LANG_OPTION,
    DEFAULT_SOURCE_LANG,
    DEFAULT_TARGET_LANG,
    LANGUAGE_CHOICES,
    TranslateGemmaParameters,
)

logger = logging.getLogger("transformers_nodes_library")


class TranslateGemmaText(ControlNode):
    """Translate text between languages using Google TranslateGemma models."""

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.params = TranslateGemmaParameters(self)
        self.params.add_input_parameters()

        # Input text
        self.add_parameter(
            ParameterString(
                name="input_text",
                tooltip="Text to translate",
                multiline=True,
                placeholder_text="Enter text to translate...",
                allow_output=False,
                ui_options={"display_name": "Input Text"},
            )
        )

        # Source language dropdown
        self.add_parameter(
            Parameter(
                name="source_lang_code",
                input_types=["str"],
                type="str",
                default_value=DEFAULT_SOURCE_LANG,
                tooltip="Source language of the input text",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                traits={Options(choices=LANGUAGE_CHOICES)},
                ui_options={"display_name": "Source Language"},
            )
        )

        # Custom source language (hidden by default)
        self.add_parameter(
            Parameter(
                name="custom_source_lang_code",
                input_types=["str"],
                type="str",
                tooltip="Enter custom ISO language code (e.g., 'pt-BR', 'zh-TW')",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={
                    "display_name": "Custom Source Code",
                    "hide": True,
                    "placeholder_text": "e.g., pt-BR",
                },
            )
        )

        # Target language dropdown
        self.add_parameter(
            Parameter(
                name="target_lang_code",
                input_types=["str"],
                type="str",
                default_value=DEFAULT_TARGET_LANG,
                tooltip="Target language for translation",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                traits={Options(choices=LANGUAGE_CHOICES)},
                ui_options={"display_name": "Target Language"},
            )
        )

        # Custom target language (hidden by default)
        self.add_parameter(
            Parameter(
                name="custom_target_lang_code",
                input_types=["str"],
                type="str",
                tooltip="Enter custom ISO language code (e.g., 'pt-BR', 'zh-TW')",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={
                    "display_name": "Custom Target Code",
                    "hide": True,
                    "placeholder_text": "e.g., de-DE",
                },
            )
        )

        # Max new tokens
        self.add_parameter(
            Parameter(
                name="max_new_tokens",
                input_types=["int"],
                type="int",
                default_value=200,
                tooltip="Maximum number of tokens to generate in the translation",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                ui_options={"display_name": "Max Tokens"},
            )
        )

        # Output text
        self.add_parameter(
            ParameterString(
                name="output_text",
                tooltip="Translated text",
                multiline=True,
                placeholder_text="",
                allowed_modes={ParameterMode.OUTPUT},
                ui_options={"display_name": "Output Text"},
            )
        )

        # Logs output
        self.params.add_logs_output_parameter()

    def after_value_set(self, parameter: Parameter, value: Any) -> None:
        """Update parameter visibility based on language selection."""
        if parameter.name == "source_lang_code":
            if value == CUSTOM_LANG_OPTION:
                self.show_parameter_by_name("custom_source_lang_code")
            else:
                self.hide_parameter_by_name("custom_source_lang_code")

        if parameter.name == "target_lang_code":
            if value == CUSTOM_LANG_OPTION:
                self.show_parameter_by_name("custom_target_lang_code")
            else:
                self.hide_parameter_by_name("custom_target_lang_code")

        return super().after_value_set(parameter, value)

    def validate_before_node_run(self) -> list[Exception] | None:
        """Validate node configuration before execution."""
        errors = []

        # Validate model is available
        model_errors = self.params.validate_before_node_run()
        if model_errors:
            errors.extend(model_errors)

        # Validate input text is provided
        input_text = self.get_parameter_value("input_text")
        if not input_text or not input_text.strip():
            errors.append(ValueError(f"{self.name}: Input text is required"))

        # Validate custom language codes if CUSTOM_LANG_OPTION is selected
        source_preset = self.get_parameter_value("source_lang_code")
        if source_preset == CUSTOM_LANG_OPTION:
            custom_source = self.get_parameter_value("custom_source_lang_code")
            if not custom_source or not custom_source.strip():
                errors.append(ValueError(f"{self.name}: Custom source language code is required"))

        target_preset = self.get_parameter_value("target_lang_code")
        if target_preset == CUSTOM_LANG_OPTION:
            custom_target = self.get_parameter_value("custom_target_lang_code")
            if not custom_target or not custom_target.strip():
                errors.append(ValueError(f"{self.name}: Custom target language code is required"))

        if errors:
            return errors
        return None

    def process(self) -> AsyncResult | None:
        yield lambda: self._process()

    def _process(self) -> None:
        input_text = self.get_parameter_value("input_text")
        source_preset = self.get_parameter_value("source_lang_code")
        custom_source = self.get_parameter_value("custom_source_lang_code") or ""
        target_preset = self.get_parameter_value("target_lang_code")
        custom_target = self.get_parameter_value("custom_target_lang_code") or ""
        max_new_tokens = self.get_parameter_value("max_new_tokens") or 200

        # Resolve language codes
        source_lang_code = TranslateGemmaParameters.get_language_code(source_preset, custom_source)
        target_lang_code = TranslateGemmaParameters.get_language_code(target_preset, custom_target)

        self.params.append_to_logs(f"Translating from {source_lang_code} to {target_lang_code}...\n")

        # Load pipeline
        self.params.append_to_logs("Loading TranslateGemma model...\n")
        pipe = self.params.load_pipeline()

        # Translate text
        self.params.append_to_logs("Translating...\n")
        translated_text = self.params.translate_text(
            pipe=pipe,
            input_text=input_text,
            source_lang_code=source_lang_code,
            target_lang_code=target_lang_code,
            max_new_tokens=max_new_tokens,
        )

        # Set output
        self.set_parameter_value("output_text", translated_text)
        self.parameter_output_values["output_text"] = translated_text

        self.params.append_to_logs("Translation complete.\n")
