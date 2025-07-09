import torch
import torch.nn as nn
import torch.nn.functional as F
from typing import Any, Dict, Optional


class FP8Linear(nn.Module):
    """FP8 Linear layer that performs computation in FP8 precision using scaled matrix multiplication."""

    def __init__(self, in_features: int, out_features: int, bias: bool = True, device=None):
        super().__init__()

        # Check FP8 support - fail fast if not supported
        self._check_fp8_support()

        self.in_features = in_features
        self.out_features = out_features

        # Store weights and bias in FP8 format for memory savings
        self.weight = nn.Parameter(torch.empty(out_features, in_features, dtype=torch.float8_e4m3fn, device=device))
        if bias:
            self.bias = nn.Parameter(torch.empty(out_features, dtype=torch.float8_e4m3fn, device=device))
        else:
            self.register_parameter("bias", None)

        # Scaling parameters for FP8 computation - same device as weights
        self.register_buffer("scale_weight", torch.ones(1, dtype=torch.float32, device=device))
        self.register_buffer("scale_input", torch.ones(1, dtype=torch.float32, device=device))

        # Cache for optimized tensor operations
        self._shape_cache = {}
        self._last_input_shape = None
        self._cached_weight_t = None

        self.reset_parameters()

    def _check_fp8_support(self):
        """Check if FP8 operations are supported on this system."""
        try:
            # Create test tensors in bfloat16 first, then convert to FP8
            # Dimensions must be divisible by 16 for FP8 hardware requirements
            # Input: (2, 16), Weight: (32, 16) -> Weight.t(): (16, 32) for (2,16) @ (16,32) = (2,32)
            test_input = torch.randn(2, 16, dtype=torch.bfloat16, device="cuda").to(torch.float8_e4m3fn)
            test_weight = torch.randn(32, 16, dtype=torch.bfloat16, device="cuda").to(torch.float8_e4m3fn)
            test_scale = torch.ones(1, dtype=torch.float32, device="cuda")
            torch._scaled_mm(test_input, test_weight.t(), scale_a=test_scale, scale_b=test_scale)
        except Exception as e:
            raise RuntimeError(f"FP8 operations not supported on this system: {e}")

    def reset_parameters(self):
        # # Initialize with standard normal distribution, then convert to FP8
        # with torch.no_grad():
        #     weight_init = torch.randn(self.out_features, self.in_features, dtype=torch.float32)
        #     self.weight.copy_(weight_init.to(torch.float8_e4m3fn))

        #     if self.bias is not None:
        #         bias_init = torch.zeros(self.out_features, dtype=torch.float32)
        #         self.bias.copy_(bias_init.to(torch.float8_e4m3fn))

        return None

    def _invalidate_cache(self):
        """Invalidate cached tensors when weights change."""
        self._cached_weight_t = None
        self._shape_cache.clear()
        self._last_input_shape = None

    def forward(self, input: torch.Tensor) -> torch.Tensor:
        original_dtype = input.dtype
        input_shape = input.shape

        # Fast path for 2D inputs (most common case)
        if len(input_shape) == 2:
            # Direct conversion to FP8 without reshaping
            input_fp8 = input.to(torch.float8_e4m3fn)

            # Cache transposed weight for repeated operations
            if self._cached_weight_t is None:
                self._cached_weight_t = self.weight.t()

            # Use torch._scaled_mm for FP8 computation
            bias_compute = self.bias.to(original_dtype) if self.bias is not None else None
            output = torch._scaled_mm(
                input_fp8,
                self._cached_weight_t,
                bias=bias_compute,
                scale_a=self.scale_input,
                scale_b=self.scale_weight,
                out_dtype=original_dtype,
            )

            # Handle tuple output from _scaled_mm
            return output[0] if isinstance(output, tuple) else output

        # Optimized path for multi-dimensional inputs
        if len(input_shape) == 1:
            raise RuntimeError(f"FP8Linear requires at least 2D input, got 1D shape {input_shape}")

        # Validate input features
        if input_shape[-1] != self.in_features:
            raise RuntimeError(
                f"Input last dimension {input_shape[-1]} doesn't match layer in_features {self.in_features}"
            )

        # Check if we can reuse cached reshape info
        shape_key = input_shape[:-1]
        if shape_key != self._last_input_shape:
            # Cache reshape dimensions for this input pattern
            self._last_input_shape = shape_key
            self._shape_cache["batch_size"] = input_shape[:-1].numel() if hasattr(input_shape[:-1], "numel") else 1
            for i, dim in enumerate(input_shape[:-1]):
                self._shape_cache["batch_size"] *= dim if i == 0 else 1
            self._shape_cache["batch_size"] = input.numel() // input_shape[-1]

        # Efficient reshape using cached batch size
        batch_size = self._shape_cache["batch_size"]
        input_2d = input.view(batch_size, input_shape[-1])

        # Convert to FP8
        input_fp8 = input_2d.to(torch.float8_e4m3fn)

        # Cache transposed weight for repeated operations
        if self._cached_weight_t is None:
            self._cached_weight_t = self.weight.t()

        # Use torch._scaled_mm for FP8 computation
        bias_compute = self.bias.to(original_dtype) if self.bias is not None else None
        output = torch._scaled_mm(
            input_fp8,
            self._cached_weight_t,
            bias=bias_compute,
            scale_a=self.scale_input,
            scale_b=self.scale_weight,
            out_dtype=original_dtype,
        )

        # Handle tuple output from _scaled_mm
        if isinstance(output, tuple):
            output = output[0]

        # Reshape back to original format using view for efficiency
        return output.view(*input_shape[:-1], self.out_features)


def replace_linear_with_fp8(module: nn.Module, name: str = "") -> nn.Module:
    """
    Recursively replace all Linear layers in a module with FP8Linear layers.

    Args:
        module: The module to modify
        name: The name of the current module (for logging)

    Returns:
        The modified module with FP8Linear layers
    """
    for attr_name, child in module.named_children():
        if isinstance(child, nn.Linear):
            # Replace Linear layer with FP8Linear
            fp8_linear = FP8Linear(
                child.in_features, child.out_features, child.bias is not None, device=child.weight.device
            )

            # Batch copy weights and bias for efficiency
            with torch.no_grad():
                # Direct copy without intermediate conversions
                fp8_linear.weight.data.copy_(child.weight.data.to(torch.float8_e4m3fn))

                if child.bias is not None:
                    fp8_linear.bias.data.copy_(child.bias.data.to(torch.float8_e4m3fn))

            # Replace the module
            setattr(module, attr_name, fp8_linear)
            print(".", end="", flush=True)  # Indicate replacement in the console
        else:
            # Recursively process child modules
            replace_linear_with_fp8(child, f"{name}.{attr_name}" if name else attr_name)

    return module


def replace_linear_with_fp8_selective(module: nn.Module, name: str = "") -> nn.Module:
    for attr_name, child in module.named_children():
        if isinstance(child, nn.Linear):
            # Skip embedding and problematic layers
            if any(
                skip_name in f"{name}.{attr_name}".lower()
                for skip_name in ["embedding", "embed", "position", "token", "vocab", "classifier", "prediction"]
            ):
                print("s", end="", flush=True)  # Skip indicator
                continue

            # Replace Linear layer with FP8Linear
            fp8_linear = FP8Linear(
                child.in_features, child.out_features, child.bias is not None, device=child.weight.device
            )

            # Batch copy weights and bias for efficiency
            with torch.no_grad():
                # Direct copy without intermediate conversions
                fp8_linear.weight.data.copy_(child.weight.data.to(torch.float8_e4m3fn))

                if child.bias is not None:
                    fp8_linear.bias.data.copy_(child.bias.data.to(torch.float8_e4m3fn))

            # Replace the module
            setattr(module, attr_name, fp8_linear)
            print(".", end="", flush=True)  # Replacement indicator
        else:
            # Recursively process child modules
            replace_linear_with_fp8_selective(child, f"{name}.{attr_name}" if name else attr_name)

    return module


class FP8LinearCompatible(FP8Linear):
    def forward(self, input: torch.Tensor) -> torch.Tensor:
        # Store original dtype
        original_dtype = input.dtype

        # Convert input to FP8
        input_fp8 = input.to(torch.float8_e4m3fn)

        # Use torch._scaled_mm for FP8 computation, but always output bfloat16
        bias_compute = self.bias.to(torch.bfloat16) if self.bias is not None else None
        return torch._scaled_mm(
            input_fp8,
            self.weight.t(),
            bias=bias_compute,
            scale_a=self.scale_input,
            scale_b=self.scale_weight,
            out_dtype=torch.bfloat16,
        )


def replace_linear_with_fp8_compatible(module: nn.Module, name: str = "") -> nn.Module:
    for attr_name, child in module.named_children():
        if isinstance(child, nn.Linear):
            # Replace Linear layer with FP8LinearCompatible
            fp8_linear = FP8LinearCompatible(child.in_features, child.out_features, child.bias is not None)

            # Batch copy weights and bias for efficiency
            with torch.no_grad():
                # Direct copy without intermediate conversions
                fp8_linear.weight.data.copy_(child.weight.data.to(torch.float8_e4m3fn))

                if child.bias is not None:
                    fp8_linear.bias.data.copy_(child.bias.data.to(torch.float8_e4m3fn))

            # Replace the module
            setattr(module, attr_name, fp8_linear)
            print(".", end="", flush=True)  # Replacement indicator
        else:
            # Recursively process child modules
            replace_linear_with_fp8_compatible(child, f"{name}.{attr_name}" if name else attr_name)

    return module


def enable_fp8_linear_layers_selective(pipeline) -> Any:
    print("Enabling FP8 Linear layers (selective) in pipeline...")
    expected_modules, _ = pipeline._get_signature_keys(pipeline.__class__)

    for module_name in expected_modules:
        if hasattr(pipeline, module_name):
            component = getattr(pipeline, module_name)
            if isinstance(component, torch.nn.Module):
                print(f"Replacing Linear layers in {module_name} with FP8Linear (selective) ", end="", flush=True)
                replace_linear_with_fp8_selective(component, module_name)
                print()

    return pipeline


def enable_fp8_linear_layers_compatible(pipeline) -> Any:
    print("Enabling FP8 Linear layers (compatible) in pipeline...")
    expected_modules, _ = pipeline._get_signature_keys(pipeline.__class__)

    for module_name in expected_modules:
        if hasattr(pipeline, module_name):
            component = getattr(pipeline, module_name)
            if isinstance(component, torch.nn.Module):
                print(f"Replacing Linear layers in {module_name} with FP8LinearCompatible ", end="", flush=True)
                replace_linear_with_fp8_compatible(component, module_name)
                print()

    return pipeline


def replace_attention_layers_with_fp8(module: nn.Module, name: str = "") -> nn.Module:
    """
    Replace only attention-related Linear layers with FP8Linear layers.
    Uses named_modules() to find all Linear layers in the hierarchy.
    """
    attention_keywords = {
        "to_q",
        "to_k",
        "to_v",
        "add_q_proj",
        "add_k_proj",
        "add_v_proj",
        "to_out",
        "to_add_out",
        "attn",
    }

    # Find all Linear modules and their parent modules
    modules_to_replace = []
    for child_name, child_module in module.named_modules():
        if isinstance(child_module, nn.Linear):
            # Check if this path contains attention keywords
            full_path = f"{name}.{child_name}" if name else child_name
            if any(keyword in full_path.lower() for keyword in attention_keywords):
                # Find parent module and attribute name
                path_parts = child_name.split(".")
                if len(path_parts) == 1:
                    # Direct child
                    parent = module
                    attr_name = path_parts[0]
                else:
                    # Nested child - find parent
                    parent = module
                    for part in path_parts[:-1]:
                        parent = getattr(parent, part)
                    attr_name = path_parts[-1]

                modules_to_replace.append((parent, attr_name, child_module, full_path))

    # Replace the modules
    for parent, attr_name, child_module, full_path in modules_to_replace:
        if not isinstance(getattr(parent, attr_name), FP8Linear):  # Don't replace twice
            fp8_linear = FP8Linear(
                child_module.in_features,
                child_module.out_features,
                child_module.bias is not None,
                device=child_module.weight.device,
            )

            # Batch copy weights and bias for efficiency
            with torch.no_grad():
                # Direct copy without intermediate conversions
                fp8_linear.weight.data.copy_(child_module.weight.data.to(torch.float8_e4m3fn))
                if child_module.bias is not None:
                    fp8_linear.bias.data.copy_(child_module.bias.data.to(torch.float8_e4m3fn))

            # Replace the module
            setattr(parent, attr_name, fp8_linear)
            print("A", end="", flush=True)  # Attention layer replaced
            print(f"\n  Replaced: {full_path}")

    return module


def enable_fp8_linear_layers(pipeline) -> Any:
    print("Enabling FP8 Linear layers in pipeline...")
    expected_modules, _ = pipeline._get_signature_keys(pipeline.__class__)

    for module_name in expected_modules:
        if hasattr(pipeline, module_name):
            component = getattr(pipeline, module_name)
            if isinstance(component, torch.nn.Module):
                print(f"Replacing Linear layers in {module_name} with FP8Linear ", end="", flush=True)
                replace_linear_with_fp8(component, module_name)
                print()

    return pipeline


class FP8ElementwiseOps:
    """FP8-storage with BF16 computation element-wise operations."""

    @staticmethod
    def _check_fp8_support():
        """Check if FP8 operations are supported."""
        try:
            test_a = torch.randn(16, 16, dtype=torch.bfloat16, device="cuda").to(torch.float8_e4m3fn)
            test_b = torch.randn(16, 16, dtype=torch.bfloat16, device="cuda").to(torch.float8_e4m3fn)
            test_scale = torch.ones(1, dtype=torch.float32, device="cuda")
            torch._scaled_mm(test_a, test_b, scale_a=test_scale, scale_b=test_scale)
            return True
        except Exception:
            return False

    @staticmethod
    def add(a: torch.Tensor, b: torch.Tensor, alpha: float = 1.0, out_dtype: torch.dtype = None) -> torch.Tensor:
        """FP8-storage optimized addition: Store in FP8, compute in BF16."""
        if out_dtype is None:
            out_dtype = a.dtype if a.dtype != torch.float8_e4m3fn else torch.bfloat16

        # Convert to FP8 for memory efficiency, then back to BF16 for computation
        a_fp8 = a.to(torch.float8_e4m3fn)
        b_fp8 = b.to(torch.float8_e4m3fn)

        # Compute in BF16 (since FP8 element-wise ops aren't supported)
        a_bf16 = a_fp8.to(torch.bfloat16)
        b_bf16 = b_fp8.to(torch.bfloat16)

        # Perform addition in BF16
        if alpha != 1.0:
            result = a_bf16 + alpha * b_bf16
        else:
            result = a_bf16 + b_bf16

        return result.to(out_dtype)

    @staticmethod
    def mul(a: torch.Tensor, b: torch.Tensor, out_dtype: torch.dtype = None) -> torch.Tensor:
        """FP8-storage optimized multiplication: Store in FP8, compute in BF16."""
        if out_dtype is None:
            out_dtype = a.dtype if a.dtype != torch.float8_e4m3fn else torch.bfloat16

        # Convert to FP8 for memory efficiency, then back to BF16 for computation
        a_fp8 = a.to(torch.float8_e4m3fn)
        b_fp8 = b.to(torch.float8_e4m3fn)

        # Compute in BF16
        a_bf16 = a_fp8.to(torch.bfloat16)
        b_bf16 = b_fp8.to(torch.bfloat16)

        # Perform multiplication in BF16
        result = a_bf16 * b_bf16

        return result.to(out_dtype)

    @staticmethod
    def fused_mul_add(a: torch.Tensor, b: torch.Tensor, c: torch.Tensor, out_dtype: torch.dtype = None) -> torch.Tensor:
        """FP8-storage optimized fused multiply-add: a * b + c"""
        if out_dtype is None:
            out_dtype = a.dtype if a.dtype != torch.float8_e4m3fn else torch.bfloat16

        # Convert to FP8 for memory efficiency, then back to BF16 for computation
        a_fp8 = a.to(torch.float8_e4m3fn)
        b_fp8 = b.to(torch.float8_e4m3fn)
        c_fp8 = c.to(torch.float8_e4m3fn)

        # Compute in BF16
        a_bf16 = a_fp8.to(torch.bfloat16)
        b_bf16 = b_fp8.to(torch.bfloat16)
        c_bf16 = c_fp8.to(torch.bfloat16)

        # Perform fused multiply-add in BF16
        result = a_bf16 * b_bf16 + c_bf16

        return result.to(out_dtype)

    @staticmethod
    def modulation(
        x: torch.Tensor, scale: torch.Tensor, shift: torch.Tensor, out_dtype: torch.dtype = None
    ) -> torch.Tensor:
        """FP8-storage optimized modulation: x * (1 + scale) + shift"""
        if out_dtype is None:
            out_dtype = x.dtype if x.dtype != torch.float8_e4m3fn else torch.bfloat16

        # Convert to FP8 for memory efficiency, then back to BF16 for computation
        x_fp8 = x.to(torch.float8_e4m3fn)
        scale_fp8 = scale.to(torch.float8_e4m3fn)
        shift_fp8 = shift.to(torch.float8_e4m3fn)

        # Compute in BF16
        x_bf16 = x_fp8.to(torch.bfloat16)
        scale_bf16 = scale_fp8.to(torch.bfloat16)
        shift_bf16 = shift_fp8.to(torch.bfloat16)

        # Perform modulation in BF16
        result = x_bf16 * (1.0 + scale_bf16) + shift_bf16

        return result.to(out_dtype)


class FP8Activations:
    """FP8-storage optimized activation functions."""

    @staticmethod
    def gelu(x: torch.Tensor, approximate: str = "none", out_dtype: torch.dtype = None) -> torch.Tensor:
        """FP8-storage optimized GELU activation."""
        if out_dtype is None:
            out_dtype = x.dtype if x.dtype != torch.float8_e4m3fn else torch.bfloat16

        # Convert to FP8 for memory efficiency, then back to BF16 for computation
        x_fp8 = x.to(torch.float8_e4m3fn)
        x_bf16 = x_fp8.to(torch.bfloat16)

        # Compute GELU in BF16
        result = F.gelu(x_bf16, approximate=approximate)
        return result.to(out_dtype)

    @staticmethod
    def silu(x: torch.Tensor, out_dtype: torch.dtype = None) -> torch.Tensor:
        """FP8-storage optimized SiLU/Swish activation."""
        if out_dtype is None:
            out_dtype = x.dtype if x.dtype != torch.float8_e4m3fn else torch.bfloat16

        # Convert to FP8 for memory efficiency, then back to BF16 for computation
        x_fp8 = x.to(torch.float8_e4m3fn)
        x_bf16 = x_fp8.to(torch.bfloat16)

        # Compute SiLU in BF16
        result = F.silu(x_bf16)
        return result.to(out_dtype)

    @staticmethod
    def relu(x: torch.Tensor, out_dtype: torch.dtype = None) -> torch.Tensor:
        """FP8-storage optimized ReLU activation."""
        if out_dtype is None:
            out_dtype = x.dtype if x.dtype != torch.float8_e4m3fn else torch.bfloat16

        # Convert to FP8 for memory efficiency, then back to BF16 for computation
        x_fp8 = x.to(torch.float8_e4m3fn)
        x_bf16 = x_fp8.to(torch.bfloat16)

        # Compute ReLU in BF16
        result = F.relu(x_bf16)
        return result.to(out_dtype)


class FP8Normalization:
    """FP8-storage optimized normalization operations."""

    @staticmethod
    def layer_norm(
        x: torch.Tensor, normalized_shape, weight=None, bias=None, eps: float = 1e-5, out_dtype: torch.dtype = None
    ) -> torch.Tensor:
        """FP8-storage optimized layer normalization."""
        if out_dtype is None:
            out_dtype = x.dtype if x.dtype != torch.float8_e4m3fn else torch.bfloat16

        # Convert to FP8 for memory efficiency, then back to BF16 for computation
        x_fp8 = x.to(torch.float8_e4m3fn)
        x_bf16 = x_fp8.to(torch.bfloat16)

        # Convert weight and bias to BF16 if provided
        weight_bf16 = weight.to(torch.bfloat16) if weight is not None else None
        bias_bf16 = bias.to(torch.bfloat16) if bias is not None else None

        # Compute layer norm in BF16
        result = F.layer_norm(x_bf16, normalized_shape, weight_bf16, bias_bf16, eps)
        return result.to(out_dtype)

    @staticmethod
    def rms_norm(
        x: torch.Tensor, scale: torch.Tensor, eps: float = 1e-6, out_dtype: torch.dtype = None
    ) -> torch.Tensor:
        """FP8-storage optimized RMS normalization."""
        if out_dtype is None:
            out_dtype = x.dtype if x.dtype != torch.float8_e4m3fn else torch.bfloat16

        # Convert to FP8 for memory efficiency, then back to BF16 for computation
        x_fp8 = x.to(torch.float8_e4m3fn)
        scale_fp8 = scale.to(torch.float8_e4m3fn)

        x_bf16 = x_fp8.to(torch.bfloat16)
        scale_bf16 = scale_fp8.to(torch.bfloat16)

        # Compute RMS norm in BF16
        variance = x_bf16.pow(2).mean(dim=-1, keepdim=True)
        normalized = x_bf16 * torch.rsqrt(variance + eps)
        result = normalized * scale_bf16

        return result.to(out_dtype)


def enable_fp8_elementwise_ops(module: nn.Module) -> nn.Module:
    """Enable FP8 element-wise operations in a module by monkey-patching."""

    # Store original functions
    if not hasattr(module, "_original_add"):
        module._original_add = torch.add
        module._original_mul = torch.mul
        module._fp8_ops_enabled = True

        # Monkey patch tensor operations
        def fp8_add(input, other, *, alpha=1, out=None):
            if out is not None:
                raise NotImplementedError("FP8 add with out parameter not supported")
            return FP8ElementwiseOps.add(input, other, alpha)

        def fp8_mul(input, other, *, out=None):
            if out is not None:
                raise NotImplementedError("FP8 mul with out parameter not supported")
            return FP8ElementwiseOps.mul(input, other)

        # Replace operations
        torch.add = fp8_add
        torch.mul = fp8_mul

    return module


def disable_fp8_elementwise_ops(module: nn.Module) -> nn.Module:
    """Disable FP8 element-wise operations by restoring original functions."""

    if hasattr(module, "_fp8_ops_enabled") and module._fp8_ops_enabled:
        # Restore original functions
        torch.add = module._original_add
        torch.mul = module._original_mul

        # Clean up
        delattr(module, "_original_add")
        delattr(module, "_original_mul")
        delattr(module, "_fp8_ops_enabled")

    return module
