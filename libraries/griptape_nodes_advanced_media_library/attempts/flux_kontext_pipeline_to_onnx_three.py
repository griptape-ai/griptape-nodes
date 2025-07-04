from optimum.exporters.onnx import main_export
from optimum.exporters.onnx.model_configs import WhisperOnnxConfig
from transformers import AutoConfig

from optimum.exporters.onnx.base import ConfigBehavior
from typing import Dict

class CustomWhisperOnnxConfig(WhisperOnnxConfig):
    @property
    def outputs(self) -> Dict[str, Dict[int, str]]:
        common_outputs = super().outputs

        if self._behavior is ConfigBehavior.ENCODER:
            for i in range(self._config.encoder_layers):
                common_outputs[f"encoder_attentions.{i}"] = {0: "batch_size"}
        elif self._behavior is ConfigBehavior.DECODER:
            for i in range(self._config.decoder_layers):
                common_outputs[f"decoder_attentions.{i}"] = {
                    0: "batch_size",
                    2: "decoder_sequence_length",
                    3: "past_decoder_sequence_length + 1"
                }
            for i in range(self._config.decoder_layers):
                common_outputs[f"cross_attentions.{i}"] = {
                    0: "batch_size",
                    2: "decoder_sequence_length",
                    3: "encoder_sequence_length_out"
                }

        return common_outputs

    @property
    def torch_to_onnx_output_map(self):
        if self._behavior is ConfigBehavior.ENCODER:
            # The encoder export uses WhisperEncoder that returns the key "attentions"
            return {"attentions": "encoder_attentions"}
        else:
            return {}

model_id = "black-forest-labs/FLUX.1-Kontext-dev"
config = AutoConfig.from_pretrained("black-forest-labs/FLUX.1-Kontext-dev", local_files_only=True)

custom_flux_kontext_onnx_config = CustomWhisperOnnxConfig(
        config=config,
        task="automatic-speech-recognition",
)

encoder_config = custom_flux_kontext_onnx_config.with_behavior("encoder")
decoder_config = custom_flux_kontext_onnx_config.with_behavior("decoder", use_past=False)
decoder_with_past_config = custom_flux_kontext_onnx_config.with_behavior("decoder", use_past=True)

custom_onnx_configs={
    "encoder_model": encoder_config,
    "decoder_model": decoder_config,
    "decoder_with_past_model": decoder_with_past_config,
}

main_export(
    model_id,
    output="custom_flux_kontext_onnx",
    no_post_process=True,
    model_kwargs={"output_attentions": True},
    custom_onnx_configs=custom_onnx_configs
)