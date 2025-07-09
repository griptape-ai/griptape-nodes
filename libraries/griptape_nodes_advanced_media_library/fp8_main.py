from fp8_export import export_fp8
from fp8_load import load_pipeline, load_fp8_pipeline, load_bf16_pipeline_as_fp8, load_bf16_pipeline_as_fp8_with_caching
from fp8_benchmark import benchmark_pipeline, print_benchmark_table

# Look at the table in https://huggingface.co/blog/diffusers-quantization
# Note how bf16 has the lowest inference time. The only operation that can
# take advantage of fp8 is _scaled_mmul. The main benefit of fp8 is lower
# VRAM usage. This equates to speed when VRAM is the bottleneck, which is
# often the case with consumer grade GPUS.
#
# The only reason we'd want to save fp8 weights (e.g. load_fp8_pipeline)
# over adding them at runtime (e.g. load_bf16_pipeline_as_fp8) is to save on
# cold start time. If you compare the two runtime speed is about the same.
# When you add a basic compile on the transformer (which takes up 90%
# of the time) we see a speedup of about 1.64x over vanilla non-compiled
# bf16 on an H100. I would expect this speedup to be higher on lower VRAM
# GPUs. Btw, although we call these fp8 weights, they are actually mixed
# precision fp8 weights. The linear layers are fp8, but that's it because
# _scaled_mmul is the only operation that can take advantage of fp8 for
# computational speedup. The rest of the model is still in bf16.
#
# The next step is to get a variant of this benchmarking script to Amaru
# to test on his 5090. We should experiment with caching the compilation
# artifacts to see if that speeds up the cold start time on second loads
# (not second inferences).
if __name__ == "__main__":
    print("Exporting FP8 model...")
    export_fp8()

    print("Loading FP8 pipeline...")
    fp8_pipeline = load_bf16_pipeline_as_fp8()
    fp8_pipeline_stats = benchmark_pipeline(fp8_pipeline)

    print("Loading FP8 pipeline with caching...")
    fp8_cached_pipeline = load_bf16_pipeline_as_fp8_with_caching()
    fp8_cached_pipeline_stats = benchmark_pipeline(fp8_cached_pipeline)

    # print("Loading standard pipeline...")
    # pipeline = load_pipeline()
    # pipeline_stats = benchmark_pipeline(pipeline)

    print("Benchmarking results:")
    print_benchmark_table(fp8_pipeline_stats, fp8_cached_pipeline_stats)
