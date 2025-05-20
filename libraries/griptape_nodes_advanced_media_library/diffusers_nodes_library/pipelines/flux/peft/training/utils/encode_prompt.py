from transformers import PreTrainedTokenizerBase, PreTrainedModel  # type: ignore[reportMissingImports]
import torch
from torch import Tensor
from typing import Optional, Union, Sequence

def _get_model_dtype(model: PreTrainedModel) -> torch.dtype:
    if hasattr(model, "module"):
        dtype = model.module.dtype
    else:
        dtype = model.dtype

    if not isinstance(dtype, torch.dtype):
        raise ValueError(f"Failed to get dtype from model: {model}. Got {dtype} instead.")

    return dtype

def _encode_prompt_with_t5(
    text_encoder: PreTrainedModel,  # e.g., T5EncoderModel or similar
    tokenizer: PreTrainedTokenizerBase,
    max_sequence_length: int = 512,
    prompt: Optional[Union[str, list[str]]] = None,
    num_images_per_prompt: int = 1,
    device: Optional[Union[str, "torch.device"]] = None,
    text_input_ids: Optional[Tensor] = None,
) -> Tensor:
    prompt = [] if prompt is None else prompt
    prompt = [prompt] if isinstance(prompt, str) else prompt
    batch_size = len(prompt)

    if tokenizer is not None:
        text_inputs = tokenizer(
            prompt,
            padding="max_length",
            max_length=max_sequence_length,
            truncation=True,
            return_length=False,
            return_overflowing_tokens=False,
            return_tensors="pt",
        )
        text_input_ids = text_inputs.input_ids

    if text_input_ids is None:
        raise ValueError("text_input_ids or tokenizer must be provided")

    prompt_embeds = text_encoder(text_input_ids.to(device))[0]

    if hasattr(text_encoder, "module"):
        dtype = text_encoder.module.dtype
    else:
        dtype = text_encoder.dtype
    prompt_embeds = prompt_embeds.to(dtype=dtype, device=device)

    _, seq_len, _ = prompt_embeds.shape

    # duplicate text embeddings and attention mask for each generation per prompt, using mps friendly method
    prompt_embeds = prompt_embeds.repeat(1, num_images_per_prompt, 1)
    prompt_embeds = prompt_embeds.view(batch_size * num_images_per_prompt, seq_len, -1)

    return prompt_embeds


def _encode_prompt_with_clip(
    text_encoder: PreTrainedModel,  # e.g., CLIPTextModel
    tokenizer: PreTrainedTokenizerBase,
    prompt: str|list[str],
    device: Optional[Union[str, "torch.device"]] = None,
    text_input_ids: Optional[Tensor] = None,
    num_images_per_prompt: int = 1,
) -> Tensor:
    prompt = [prompt] if isinstance(prompt, str) else prompt
    batch_size = len(prompt)

    if tokenizer is not None:
        text_inputs = tokenizer(
            prompt,
            padding="max_length",
            max_length=77,
            truncation=True,
            return_overflowing_tokens=False,
            return_length=False,
            return_tensors="pt",
        )

        text_input_ids = text_inputs.input_ids
    
    if text_input_ids is None:
        raise ValueError("text_input_ids or tokenizer must be provided")

    prompt_embeds = text_encoder(text_input_ids.to(device), output_hidden_states=False)

    if hasattr(text_encoder, "module"):
        dtype = text_encoder.module.dtype
    else:
        dtype = text_encoder.dtype
    # Use pooled output of CLIPTextModel
    prompt_embeds = prompt_embeds.pooler_output
    prompt_embeds = prompt_embeds.to(dtype=dtype, device=device)

    # duplicate text embeddings for each generation per prompt, using mps friendly method
    prompt_embeds = prompt_embeds.repeat(1, num_images_per_prompt, 1)
    prompt_embeds = prompt_embeds.view(batch_size * num_images_per_prompt, -1)

    return prompt_embeds


def encode_prompt(
    text_encoders: Sequence[PreTrainedModel],
    tokenizers: Sequence[PreTrainedTokenizerBase],
    prompt: str|list[str],
    max_sequence_length: int,
    device: Optional[Union[str, "torch.device"]] = None,
    num_images_per_prompt: int = 1,
    text_input_ids_list: Optional[Sequence[Optional[Tensor]]] = None,
) -> Sequence[Tensor]:
    prompt = [prompt] if isinstance(prompt, str) else prompt

    pooled_prompt_embeds = _encode_prompt_with_clip(
        text_encoder=text_encoders[0],
        tokenizer=tokenizers[0],
        prompt=prompt,
        device=device if device is not None else text_encoders[0].device,
        num_images_per_prompt=num_images_per_prompt,
        text_input_ids=text_input_ids_list[0] if text_input_ids_list else None,
    )

    prompt_embeds = _encode_prompt_with_t5(
        text_encoder=text_encoders[1],
        tokenizer=tokenizers[1],
        max_sequence_length=max_sequence_length,
        prompt=prompt,
        num_images_per_prompt=num_images_per_prompt,
        device=device if device is not None else text_encoders[1].device,
        text_input_ids=text_input_ids_list[1] if text_input_ids_list else None,
    )

    dtype = _get_model_dtype(text_encoders[0])
    text_ids = torch.zeros(prompt_embeds.shape[1], 3).to(device=device, dtype=dtype)

    return prompt_embeds, pooled_prompt_embeds, text_ids


