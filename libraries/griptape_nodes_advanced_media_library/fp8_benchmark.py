import time
from typing import Any


def benchmark_pipeline(
    pipeline,
    prompt: str = "A beautiful landscape",
    num_runs: int = 3,
    num_inference_steps: int = 4,
    model_loading_time: float = 0.0,
    **kwargs,
) -> dict[str, Any]:
    # Warm up
    print("Warming up pipeline...")
    _ = pipeline(prompt=prompt, num_inference_steps=1, **kwargs)

    # Benchmark
    print(f"Running {num_runs} benchmark iterations...")
    times = []

    for i in range(num_runs):
        start_time = time.time()
        _ = pipeline(prompt=prompt, num_inference_steps=num_inference_steps, **kwargs)
        end_time = time.time()
        times.append(end_time - start_time)
        print(f"Run {i + 1}/{num_runs}: {times[-1]:.2f}s")

    # Calculate statistics
    avg_time = sum(times) / len(times)
    min_time = min(times)
    max_time = max(times)

    return {
        "average_time": avg_time,
        "min_time": min_time,
        "max_time": max_time,
        "all_times": times,
        "model_loading_time": model_loading_time,
    }


def print_benchmark_table(standard_stats: dict[str, Any], fp8_stats: dict[str, Any]) -> None:
    """Print benchmark results in a formatted table."""
    print("\n" + "=" * 60)
    print("BENCHMARK RESULTS")
    print("=" * 60)
    print(f"{'Metric':<20} {'Standard':<15} {'FP8':<15} {'Speedup':<10}")
    print("-" * 60)

    # Model loading time comparison
    std_loading_time = standard_stats.get("model_loading_time", 0.0)
    fp8_loading_time = fp8_stats.get("model_loading_time", 0.0)
    loading_speedup = std_loading_time / fp8_loading_time if fp8_loading_time > 0 else 0.0

    print(
        f"{'Loading Time (s)':<20} {std_loading_time:<15.2f} {fp8_loading_time:<15.2f} {loading_speedup:<10.2f}x"
    )

    # Inference time comparison
    avg_speedup = standard_stats["average_time"] / fp8_stats["average_time"]
    min_speedup = standard_stats["min_time"] / fp8_stats["min_time"]
    max_speedup = standard_stats["max_time"] / fp8_stats["max_time"]

    print(
        f"{'Average Time (s)':<20} {standard_stats['average_time']:<15.2f} {fp8_stats['average_time']:<15.2f} {avg_speedup:<10.2f}x"
    )
    print(
        f"{'Min Time (s)':<20} {standard_stats['min_time']:<15.2f} {fp8_stats['min_time']:<15.2f} {min_speedup:<10.2f}x"
    )
    print(
        f"{'Max Time (s)':<20} {standard_stats['max_time']:<15.2f} {fp8_stats['max_time']:<15.2f} {max_speedup:<10.2f}x"
    )
    print("=" * 60)

    print("\nDetailed Times:")
    print(f"Standard: {[f'{t:.2f}' for t in standard_stats['all_times']]}")
    print(f"FP8:      {[f'{t:.2f}' for t in fp8_stats['all_times']]}")
