import torch
import torch.profiler
from fp8_load import load_pipeline, load_fp8_pipeline


def profile_pipeline(pipeline, name: str, prompt: str = "A beautiful landscape", num_inference_steps: int = 4):
    """Profile a pipeline and save detailed timing information."""
    print(f"Profiling {name}...")

    # Warm up
    print("Warming up...")
    _ = pipeline(prompt=prompt, num_inference_steps=1)

    # Profile
    print("Running profiler...")
    with torch.profiler.profile(
        activities=[torch.profiler.ProfilerActivity.CPU, torch.profiler.ProfilerActivity.CUDA],
        record_shapes=True,
        with_stack=True,
        with_modules=True,
    ) as prof:
        _ = pipeline(prompt=prompt, num_inference_steps=num_inference_steps)

    # Save trace file
    trace_file = f"trace_{name.lower().replace(' ', '_')}.json"
    prof.export_chrome_trace(trace_file)
    print(f"Trace saved to {trace_file} (open in chrome://tracing)")

    # Print top operations by CUDA time
    print(f"\n=== Top 20 Operations by CUDA Time ({name}) ===")
    print(prof.key_averages().table(sort_by="cuda_time_total", row_limit=20))

    # Print module-level breakdown
    print(f"\n=== Module Breakdown ({name}) ===")
    print(prof.key_averages(group_by_stack_n=5).table(sort_by="cuda_time_total", row_limit=10))

    return prof


if __name__ == "__main__":
    print("Loading standard pipeline...")
    standard_pipeline = load_pipeline()

    print("Loading FP8 pipeline...")
    fp8_pipeline = load_fp8_pipeline()

    # Profile both pipelines
    standard_prof = profile_pipeline(standard_pipeline, "Standard Pipeline")
    fp8_prof = profile_pipeline(fp8_pipeline, "FP8 Pipeline")

    print("\n" + "=" * 60)
    print("PROFILING COMPLETE")
    print("=" * 60)
    print("View detailed traces in Chrome:")
    print("1. Open chrome://tracing")
    print("2. Load trace_standard_pipeline.json")
    print("3. Load trace_fp8_pipeline.json")
    print("4. Compare timing differences")
