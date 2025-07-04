import torch

def convert(pipeline, dtype: torch.dtype):
    # Get expected modules for this pipeline class
    expected_modules, _ = pipeline._get_signature_keys(pipeline.__class__)
    
    # Convert weights to FP8 for all nn.Module components
    modules_total = 0
    modules_converted = 0
    for module_name in expected_modules:
        if hasattr(pipeline, module_name):
            component = getattr(pipeline, module_name)
            modules_total += 1
            if isinstance(component, torch.nn.Module):
                modules_converted += 1
                for param_name, param in component.named_parameters():
                    param.data = param.data.to(dtype)

    print(f"Converted {modules_converted} out of {modules_total} modules to {dtype}.")

    return pipeline
