from pathlib import Path
import diffusers
import torch
from fp8_convert import convert
from fp8_ops import replace_linear_with_fp8, replace_attention_layers_with_fp8
from torch_compile_optimizer import TorchCompileOptimizer, create_sample_inputs_for_flux

device = "cuda"

model_id = "black-forest-labs/FLUX.1-dev"
fp8_model_directory = Path(__file__).parent / "FLUX.1-dev-fp8"
PipelineClass = diffusers.FluxPipeline

# model_id = "black-forest-labs/FLUX.1-Kontext-dev"
# fp8_model_directory = Path(__file__).parent / "FLUX.1-Kontext-dev-fp8"
# PipelineClass = diffusers.FluxKontextPipeline

def load_pipeline_as_fp8_with_caching():
    pipeline = PipelineClass.from_pretrained(
        model_id,
        torch_dtype=torch.bfloat16,
        local_files_only=True
    ).to(device)
    
    # A trival compile: `fp8_pipeline.transformer` seems better than the stuff below so far.
    # but it need to take advantage of compile artifact caching to be justifiable.
    #
    # # Compile transformer with fast mode for additional speedupe
    print("Compiling transformer with fast mode...")
    optimizer = TorchCompileOptimizer()
    pipeline.transformer = optimizer.compile_transformer(pipeline.transformer)
    print("Compilation completed!")
    pipeline.transformer.compile()
    
    return pipeline

def load_pipeline():
    pipeline = PipelineClass.from_pretrained(
        model_id,
        torch_dtype=torch.bfloat16,
        local_files_only=True
    ).to(device)
    return pipeline

def load_fp8_pipeline():
    # Still having trouble loading the model when only some of the layers are saved in fp8.
    print(f"Loading FP8 pipeline from {fp8_model_directory}")
    fp8_pipeline = PipelineClass.from_pretrained(
        str(fp8_model_directory),
        torch_dtype=torch.bfloat16,
        local_files_only=True,
    ).to(device)

    # Apply FP8Linear architecture (weights are already FP8 from export)
    print("Applying FP8Linear layers...")
    fp8_pipeline.transformer = replace_linear_with_fp8(fp8_pipeline.transformer)
    print()

    # A trival compile: `fp8_pipeline.transformer` seems better than the stuff below so far.
    # but it need to take advantage of compile artifact caching to be justifiable.
    
    optimizer = TorchCompileOptimizer()

    fp8_pipeline.transformer.compile()

    # Warm up: 
    sample_inputs = create_sample_inputs_for_flux()
    optimizer.warmup_compiled_model(fp8_pipeline.transformer, sample_inputs)
    # Add in compile artifact caching 

    return fp8_pipeline


def load_bf16_pipeline_as_fp8_with_caching():
    print(f"Loading BF16 pipeline from {model_id}")
    pipeline = PipelineClass.from_pretrained(
        model_id,
        torch_dtype=torch.bfloat16,
        local_files_only=True
    ).to(device)

    # Setup Torch Caching
    optimizer = TorchCompileOptimizer()

    print("Applying FP8 to all linear layers...")
    pipeline.transformer = replace_linear_with_fp8(pipeline.transformer)
    
    print("\nApplying FP8 to attention layers...")
    pipeline.transformer = replace_attention_layers_with_fp8(pipeline.transformer)

    #Adding in torch compilation here
    pipeline.transformer.compile()

    sample_inputs = create_sample_inputs_for_flux()
    optimizer.warmup_compiled_model(pipeline.transformer, sample_inputs)


    return pipeline

def load_bf16_pipeline_as_fp8():
    print(f"Loading BF16 pipeline from {model_id}")
    pipeline = PipelineClass.from_pretrained(
        model_id,
        torch_dtype=torch.bfloat16,
        local_files_only=True
    ).to(device)


    print("Applying FP8 to all linear layers...")
    pipeline.transformer = replace_linear_with_fp8(pipeline.transformer)
    
    print("\nApplying FP8 to attention layers...")
    pipeline.transformer = replace_attention_layers_with_fp8(pipeline.transformer)


    return pipeline


def load_bnb_int4_pipeline():
    print(f"Loading bnb 4bit pipeline from {model_id}")
    pipeline = PipelineClass.from_pretrained(
        "diffusers/FLUX.1-dev-bnb-4bit",
        torch_dtype=torch.bfloat16
    )
    pipeline.to(device)
    return pipeline