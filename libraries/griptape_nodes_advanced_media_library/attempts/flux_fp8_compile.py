





def load_bf16_pipeline_as_fp8_with_caching():
    print(f"Loading BF16 pipeline from {model_id}")
    pipeline = PipelineClass.from_pretrained(model_id, torch_dtype=torch.bfloat16, local_files_only=True).to(device)

    # Setup Torch Caching
    optimizer = TorchCompileOptimizer()

    print("Applying FP8 to all linear layers...")
    pipeline.transformer = replace_linear_with_fp8(pipeline.transformer)

    print("\nApplying FP8 to attention layers...")
    pipeline.transformer = replace_attention_layers_with_fp8(pipeline.transformer)

    # Adding in torch compilation here
    pipeline.transformer.compile()

    sample_inputs = create_sample_inputs_for_flux()
    optimizer.warmup_compiled_model(pipeline.transformer, sample_inputs)

    return pipeline