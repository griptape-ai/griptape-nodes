import copy
import torch
import diffusers
from torchao.quantization import int4_weight_only, quantize_
from torchao.utils import benchmark_model

# Load the FluxKontextPipeline
pipe = diffusers.FluxKontextPipeline.from_pretrained(
    pretrained_model_name_or_path="black-forest-labs/FLUX.1-Kontext-dev",
    local_files_only=True,
)

# Move to GPU and set to eval mode
pipe = pipe.to("cuda").to(torch.bfloat16)
pipe.transformer.eval()

# Create a copy for bf16 comparison
pipe_bf16 = copy.deepcopy(pipe)

# Apply int4 quantization to the transformer
quantize_(pipe.transformer, int4_weight_only(group_size=32))

print("pipe.transformer after quantization:", pipe.transformer)

# Prepare example inputs for benchmarking
# FluxKontextPipeline typically expects these inputs
example_inputs = {
    "prompt": "A beautiful landscape",
    "height": 1024,
    "width": 1024,
    "num_inference_steps": 50,
    "guidance_scale": 7.5,
    "output_type": "pt",  # Return tensors instead of PIL images for benchmarking
}

num_runs = 10  # Reduced runs since diffusion models are slower
torch._dynamo.reset()


# Benchmark function for diffusion models
def benchmark_diffusion_model(pipe, num_runs, inputs):
    torch.cuda.synchronize()
    start_time = torch.cuda.Event(enable_timing=True)
    end_time = torch.cuda.Event(enable_timing=True)

    times = []
    for _ in range(num_runs):
        start_time.record()
        with torch.no_grad():
            _ = pipe(**inputs)
        end_time.record()
        torch.cuda.synchronize()
        times.append(start_time.elapsed_time(end_time))

    return sum(times) / len(times)


# Run benchmarks
print("Running bf16 benchmark...")
bf16_time = benchmark_diffusion_model(pipe_bf16, num_runs, example_inputs)

print("Running int4 benchmark...")
int4_time = benchmark_diffusion_model(pipe, num_runs, example_inputs)

print("bf16 mean time: %0.3f ms" % bf16_time)
print("int4 mean time: %0.3f ms" % int4_time)
print("speedup: %0.1fx" % (bf16_time / int4_time))
