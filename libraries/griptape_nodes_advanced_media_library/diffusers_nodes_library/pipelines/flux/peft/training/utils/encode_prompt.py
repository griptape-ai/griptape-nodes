from typing import Union

import torch  # type: ignore[reportMissingImports]
from torch import Tensor  # type: ignore[reportMissingImports]
from transformers import PreTrainedModel, PreTrainedTokenizerBase  # type: ignore[reportMissingImports]


def encode_prompt(  # noqa: PLR0913
    clip_tokenizer: PreTrainedTokenizerBase,
    t5_tokenizer: PreTrainedTokenizerBase,
    clip_text_encoder: PreTrainedModel,
    t5_text_encoder: PreTrainedModel,
    prompt: str | list[str],
    max_sequence_length: int,
    device: Union[str, "torch.device"] | None = None,
    num_images_per_prompt: int = 1,
) -> tuple[Tensor, Tensor, Tensor]:
    """Encodes a prompt using multiple text encoders (e.g., CLIP and T5) and returns the embeddings."""
    prompt = [prompt] if isinstance(prompt, str) else prompt
    batch_size = len(prompt)

    pooled_text_input_ids, text_input_ids = tokenize_prompt(
        clip_tokenizer,
        t5_tokenizer,
        prompt=prompt,
        max_sequence_length=max_sequence_length,
    )

    return encode_tokens(
        clip_text_encoder,
        t5_text_encoder,
        pooled_text_input_ids=pooled_text_input_ids,
        text_input_ids=text_input_ids,
        batch_size=batch_size,
        num_images_per_prompt=num_images_per_prompt,
        device=device,
    )


def tokenize_prompt(
    clip_tokenizer: PreTrainedTokenizerBase,
    t5_tokenizer: PreTrainedTokenizerBase,
    prompt: str | list[str],
    max_sequence_length: int = 512,
) -> tuple[Tensor, Tensor]:
    """Tokenizes a prompt using multiple tokenizers and returns the input IDs and batch size."""
    prompt = [prompt] if isinstance(prompt, str) else prompt

    pooled_text_input_ids = tokenize_prompt_with_clip(clip_tokenizer, prompt)
    text_input_ids = tokenize_prompt_with_t5(t5_tokenizer, prompt=prompt, max_sequence_length=max_sequence_length)

    return pooled_text_input_ids, text_input_ids


def encode_tokens(  # noqa: PLR0913
    clip_text_encoder: PreTrainedModel,
    t5_text_encoder: PreTrainedModel,
    pooled_text_input_ids: Tensor,
    text_input_ids: Tensor,
    batch_size: int,
    num_images_per_prompt: int = 1,
    device: Union[str, "torch.device"] | None = None,
) -> tuple[Tensor, Tensor, Tensor]:
    """Encodes text input IDs using multiple text encoders and returns the embeddings."""
    device = device or clip_text_encoder.device
    dtype = _get_model_dtype(clip_text_encoder)

    pooled_prompt_embeds = encode_tokens_with_clip(
        clip_text_encoder,
        pooled_text_input_ids,
        batch_size,
        num_images_per_prompt,
        device=device,
    )
    prompt_embeds = encode_tokens_with_t5(t5_text_encoder, text_input_ids, batch_size, num_images_per_prompt, device)

    text_ids = torch.zeros(prompt_embeds.shape[1], 3).to(device=device, dtype=dtype)

    return prompt_embeds, pooled_prompt_embeds, text_ids


def tokenize_prompt_with_t5(
    tokenizer: PreTrainedTokenizerBase,
    prompt: str | list[str],
    max_sequence_length: int = 512,
) -> Tensor:
    """Tokenizes a prompt using a T5 tokenizer and returns the input IDs and batch size."""
    prompt = [prompt] if isinstance(prompt, str) else prompt

    text_inputs = tokenizer(
        prompt,
        padding="max_length",
        max_length=max_sequence_length,
        truncation=True,
        return_length=False,
        return_overflowing_tokens=False,
        return_tensors="pt",
    )
    return text_inputs.input_ids


def encode_tokens_with_t5(
    text_encoder: PreTrainedModel,
    text_input_ids: Tensor,
    batch_size: int,
    num_images_per_prompt: int = 1,
    device: Union[str, "torch.device"] | None = None,
) -> Tensor:
    """Encodes text input IDs using a T5 text encoder and returns the embeddings."""
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


def tokenize_prompt_with_clip(
    tokenizer: PreTrainedTokenizerBase,
    prompt: str | list[str],
) -> Tensor:
    """Tokenizes a prompt using a CLIP tokenizer and returns the input IDs and batch size."""
    prompt = [] if prompt is None else prompt
    prompt = [prompt] if isinstance(prompt, str) else prompt

    text_inputs = tokenizer(
        prompt,
        padding="max_length",
        max_length=77,
        truncation=True,
        return_overflowing_tokens=False,
        return_length=False,
        return_tensors="pt",
    )

    return text_inputs.input_ids


def encode_tokens_with_clip(
    text_encoder: PreTrainedModel,
    text_input_ids: Tensor,
    batch_size: int,
    num_images_per_prompt: int = 1,
    device: Union[str, "torch.device"] | None = None,
) -> Tensor:
    """Encodes text input IDs using a CLIP text encoder and returns the embeddings."""
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


def _get_model_dtype(model: PreTrainedModel) -> torch.dtype:
    if hasattr(model, "module"):
        dtype = model.module.dtype
    else:
        dtype = model.dtype

    if not isinstance(dtype, torch.dtype):
        msg = f"Failed to get dtype from model: {model}. Got {dtype} instead."
        raise TypeError(msg)

    return dtype
