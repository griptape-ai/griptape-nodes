import torch
from fp8_load import load_pipeline
from fp8_load import fp8_model_directory
from fp8_ops import replace_linear_with_fp8


def export_fp8():
    if fp8_model_directory.exists():
        print(f"FP8 model directory {fp8_model_directory} already exists. Skipping export.")
        return
    
    pipeline = load_pipeline()

    print("Converting Linear layers to FP8...")
    # Only convert Linear layers to FP8, keep everything else in BF16
    pipeline.transformer = replace_linear_with_fp8(pipeline.transformer)
    print()  # New line after progress dots
    
    # Save the pipeline - now only Linear weights are FP8, rest are BF16
    print(f"Saving FP8 pipeline to {fp8_model_directory}")
    pipeline.save_pretrained(fp8_model_directory, safe_serialization=True)
    
    print("FP8 export completed!")
    print("- Linear layer weights: FP8 format (50% memory reduction)")
    print("- Other weights (embeddings, norms): BF16 format (full precision)")