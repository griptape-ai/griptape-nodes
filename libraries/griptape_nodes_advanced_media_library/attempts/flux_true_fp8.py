import copy
import torch


class ToyLinearModel(torch.nn.Module):
    def __init__(self, m: int, n: int, k: int):
        super().__init__()
        self.linear1 = torch.nn.Linear(m, n, bias=False)
        self.linear2 = torch.nn.Linear(n, k, bias=False)

    def forward(self, x):
        x = self.linear1(x)
        x = self.linear2(x)
        return x


model = ToyLinearModel(1024, 1024, 1024).eval().to(torch.bfloat16).to("cuda")
model_bf16 = copy.deepcopy(model)

from torchao.quantization import int4_weight_only, quantize_

quantize_(model, int4_weight_only(group_size=32))

print("model.linear1", model.linear1)
print("model.linear2", model.linear2)

from torchao.utils import benchmark_model


num_runs = 100
torch._dynamo.reset()
example_inputs = (torch.randn(1, 1024, dtype=torch.bfloat16, device="cuda"),)
int4_time = benchmark_model(model, num_runs, example_inputs)
bf16_time = benchmark_model(model_bf16, num_runs, example_inputs)


print("bf16 mean time: %0.3f ms" % bf16_time)
print("int4 mean time: %0.3f ms" % int4_time)
print("speedup: %0.1fx" % (bf16_time / int4_time))
