import torch
import time
from torch_compile_optimizer import TorchCompileOptimizer, create_sample_inputs_for_flux
from fp8_load import load_pipeline, load_fp8_pipeline
from fp8_benchmark import benchmark_pipeline, print_benchmark_table


def benchmark_torch_compile_modes(pipeline_func, sample_inputs, modes=None):
    """Benchmark different torch.compile modes on a pipeline."""

    if modes is None:
        modes = ["default", "reduce-overhead", "max-autotune", "max-autotune-no-cudagraphs", "custom"]

    optimizer = TorchCompileOptimizer()
    results = {}

    print("=" * 80)
    print("TORCH.COMPILE MODE COMPARISON")
    print("=" * 80)

    # Baseline - no compilation
    print("\nTesting baseline (no compilation)...")
    baseline_pipeline = pipeline_func()
    baseline_time = benchmark_single_mode(baseline_pipeline, sample_inputs, "baseline")
    results["baseline"] = baseline_time

    # Test each compilation mode
    for mode in modes:
        print(f"\nTesting mode: {mode}")
        try:
            # Load fresh pipeline
            pipeline = pipeline_func()

            # Compile with specific mode
            if mode == "custom":
                compiled_pipeline = optimizer.compile_transformer(pipeline.transformer, mode=mode)
                pipeline.transformer = compiled_pipeline
            else:
                compiled_pipeline = optimizer.compile_transformer(pipeline.transformer, mode=mode)
                pipeline.transformer = compiled_pipeline

            # Warmup
            print("Warming up compiled model...")
            optimizer.warmup_compiled_model(pipeline.transformer, create_sample_inputs_for_flux())

            # Benchmark
            mode_time = benchmark_single_mode(pipeline, sample_inputs, mode)
            results[mode] = mode_time

        except Exception as e:
            print(f"Mode {mode} failed: {e}")
            results[mode] = None

    # Print results
    print("\n" + "=" * 80)
    print("TORCH.COMPILE RESULTS")
    print("=" * 80)
    print(f"{'Mode':<25} {'Time (s)':<12} {'Speedup':<10} {'Status'}")
    print("-" * 80)

    baseline_time_val = results["baseline"] if results["baseline"] else float("inf")

    for mode, time_val in results.items():
        if time_val is not None:
            speedup = baseline_time_val / time_val
            status = "✓"
        else:
            speedup = 0.0
            status = "✗ Failed"

        time_str = f"{time_val:.4f}" if time_val else "N/A"
        print(f"{mode:<25} {time_str:<12} {speedup:<10.2f}x {status}")

    return results


def benchmark_single_mode(pipeline, sample_inputs, mode_name, num_runs=3):
    """Benchmark a single compilation mode."""

    # Create sample prompt and settings
    prompt = "A beautiful landscape with mountains and a lake"

    print(f"Running {num_runs} benchmark iterations for {mode_name}...")
    times = []

    for i in range(num_runs):
        torch.cuda.synchronize()
        start_time = time.time()

        try:
            with torch.no_grad():
                _ = pipeline(
                    prompt=prompt,
                    num_inference_steps=4,
                    guidance_scale=3.5,
                    max_sequence_length=256,
                    generator=torch.Generator().manual_seed(42),
                )
                torch.cuda.synchronize()
        except Exception as e:
            print(f"Run {i + 1} failed: {e}")
            continue

        end_time = time.time()
        run_time = end_time - start_time
        times.append(run_time)
        print(f"  Run {i + 1}/{num_runs}: {run_time:.2f}s")

    if times:
        avg_time = sum(times) / len(times)
        print(f"Average time for {mode_name}: {avg_time:.4f}s")
        return avg_time
    else:
        print(f"All runs failed for {mode_name}")
        return None


def benchmark_compilation_strategies():
    """Benchmark different compilation strategies (whole model vs individual layers)."""

    optimizer = TorchCompileOptimizer()

    print("=" * 80)
    print("COMPILATION STRATEGY COMPARISON")
    print("=" * 80)

    strategies = {
        "baseline": lambda p: p,  # No compilation
        "whole_transformer": lambda p: setattr(
            p, "transformer", optimizer.compile_transformer(p.transformer, "max-autotune")
        )
        or p,
        "individual_layers": lambda p: setattr(
            p, "transformer", optimizer.compile_individual_layers(p.transformer, "max-autotune")
        )
        or p,
        "attention_only": lambda p: setattr(
            p, "transformer", optimizer.compile_attention_layers(p.transformer, "max-autotune")
        )
        or p,
    }

    results = {}

    for strategy_name, strategy_func in strategies.items():
        print(f"\nTesting strategy: {strategy_name}")

        try:
            # Load fresh pipeline
            pipeline = load_pipeline()

            # Apply compilation strategy
            pipeline = strategy_func(pipeline)

            # Warmup if compiled
            if strategy_name != "baseline":
                print("Warming up...")
                optimizer.warmup_compiled_model(pipeline.transformer, create_sample_inputs_for_flux())

            # Benchmark
            time_val = benchmark_single_mode(pipeline, {}, strategy_name, num_runs=2)
            results[strategy_name] = time_val

        except Exception as e:
            print(f"Strategy {strategy_name} failed: {e}")
            results[strategy_name] = None

    # Print comparison
    print("\n" + "=" * 60)
    print("STRATEGY COMPARISON")
    print("=" * 60)
    print(f"{'Strategy':<20} {'Time (s)':<12} {'Speedup':<10}")
    print("-" * 60)

    baseline_time = results.get("baseline", float("inf"))

    for strategy, time_val in results.items():
        if time_val is not None:
            speedup = baseline_time / time_val if baseline_time else 0
            print(f"{strategy:<20} {time_val:<12.4f} {speedup:<10.2f}x")
        else:
            print(f"{strategy:<20} {'Failed':<12} {'N/A':<10}")

    return results


def benchmark_compile_with_fp8():
    """Benchmark torch.compile combined with FP8 optimizations."""

    optimizer = TorchCompileOptimizer()

    print("=" * 80)
    print("TORCH.COMPILE + FP8 COMBINATION")
    print("=" * 80)

    combinations = {
        "baseline": lambda: load_pipeline(),
        "fp8_only": lambda: load_fp8_pipeline(),
        "compile_only": lambda: compile_pipeline(load_pipeline(), optimizer),
        "fp8_and_compile": lambda: compile_pipeline(load_fp8_pipeline(), optimizer),
    }

    results = {}

    for combo_name, combo_func in combinations.items():
        print(f"\nTesting combination: {combo_name}")

        try:
            pipeline = combo_func()

            # Warmup compiled models
            if "compile" in combo_name:
                print("Warming up compiled components...")
                optimizer.warmup_compiled_model(pipeline.transformer, create_sample_inputs_for_flux())

            # Benchmark
            time_val = benchmark_single_mode(pipeline, {}, combo_name, num_runs=2)
            results[combo_name] = time_val

        except Exception as e:
            print(f"Combination {combo_name} failed: {e}")
            results[combo_name] = None

    # Print results
    print("\n" + "=" * 60)
    print("FP8 + COMPILE COMBINATION RESULTS")
    print("=" * 60)

    baseline_time = results.get("baseline", float("inf"))

    for combo, time_val in results.items():
        if time_val is not None:
            speedup = baseline_time / time_val if baseline_time else 0
            memory_info = get_memory_usage()
            print(f"{combo:<20} {time_val:<12.4f} {speedup:<10.2f}x Mem: {memory_info:.1f}GB")
        else:
            print(f"{combo:<20} {'Failed':<12} {'N/A':<10}")

    return results


def compile_pipeline(pipeline, optimizer):
    """Helper to compile a pipeline's transformer."""
    pipeline.transformer = optimizer.compile_transformer(pipeline.transformer, "max-autotune")
    return pipeline


def get_memory_usage():
    """Get current GPU memory usage in GB."""
    if torch.cuda.is_available():
        return torch.cuda.memory_allocated() / (1024**3)
    return 0.0


def run_cache_persistence_test():
    """Test that torch.compile cache persists across runs."""

    print("=" * 80)
    print("CACHE PERSISTENCE TEST")
    print("=" * 80)

    optimizer = TorchCompileOptimizer()

    # First run - should populate cache
    print("First run (populating cache)...")
    start_time = time.time()

    pipeline = load_pipeline()
    compiled_transformer = optimizer.compile_transformer(pipeline.transformer, "max-autotune")

    # Trigger compilation
    sample_inputs = create_sample_inputs_for_flux()
    optimizer.warmup_compiled_model(compiled_transformer, sample_inputs)

    first_run_time = time.time() - start_time
    cache_info_after_first = optimizer.get_cache_info()

    print(f"First run time: {first_run_time:.2f}s")
    print(f"Cache after first run: {cache_info_after_first}")

    # Clear the model but keep cache
    del pipeline, compiled_transformer
    torch.cuda.empty_cache()

    # Second run - should use cache
    print("\nSecond run (using cache)...")
    start_time = time.time()

    pipeline = load_pipeline()
    compiled_transformer = optimizer.compile_transformer(pipeline.transformer, "max-autotune")

    # Trigger compilation (should be faster due to cache)
    optimizer.warmup_compiled_model(compiled_transformer, sample_inputs)

    second_run_time = time.time() - start_time
    cache_info_after_second = optimizer.get_cache_info()

    print(f"Second run time: {second_run_time:.2f}s")
    print(f"Cache after second run: {cache_info_after_second}")

    speedup = first_run_time / second_run_time if second_run_time > 0 else 0
    print(f"\nCache speedup: {speedup:.2f}x")

    return {
        "first_run_time": first_run_time,
        "second_run_time": second_run_time,
        "cache_speedup": speedup,
        "cache_size_mb": cache_info_after_second.get("cache_size_mb", 0),
    }


if __name__ == "__main__":
    print("Starting comprehensive torch.compile benchmarks...")

    # Test 1: Cache persistence
    cache_results = run_cache_persistence_test()

    # Test 2: Different compilation modes
    # modes_results = benchmark_torch_compile_modes(load_pipeline, {})

    # Test 3: Different compilation strategies
    # strategy_results = benchmark_compilation_strategies()

    # Test 4: FP8 + Compile combinations
    # combo_results = benchmark_compile_with_fp8()

    print("\n" + "=" * 80)
    print("FINAL SUMMARY")
    print("=" * 80)
    print(f"Cache persistence test completed: {cache_results['cache_speedup']:.2f}x speedup")
    print("Run individual benchmarks by uncommenting the test functions above.")
