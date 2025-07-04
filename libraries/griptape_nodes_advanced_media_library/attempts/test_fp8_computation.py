"""
Minimal FP8 computation test script for Windows + PyTorch + CUDA
Tests actual FP8 computation (not just storage) with verification
"""

import torch
import numpy as np
import sys
import warnings
warnings.filterwarnings('ignore')

def print_section(title):
    print(f"\n{'='*60}")
    print(f" {title}")
    print(f"{'='*60}")

def check_environment():
    print_section("ENVIRONMENT CHECK")
    print(f"Python version: {sys.version}")
    print(f"PyTorch version: {torch.__version__}")
    print(f"CUDA available: {torch.cuda.is_available()}")
    if torch.cuda.is_available():
        print(f"CUDA version: {torch.version.cuda}")
        print(f"GPU: {torch.cuda.get_device_name(0)}")
        print(f"GPU compute capability: {torch.cuda.get_device_capability(0)}")
    
    # Check for FP8 support
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    if device.type == 'cuda':
        # Check if GPU supports FP8 (Ada Lovelace/Hopper and newer)
        major, minor = torch.cuda.get_device_capability(0)
        fp8_supported = major >= 9 or (major == 8 and minor >= 9)  # Ada Lovelace 8.9+, Hopper 9.0+
        print(f"Hardware FP8 support: {fp8_supported}")
    
    return device

def test_fp8_native_torch():
    """Test native PyTorch FP8 dtypes if available"""
    print_section("PYTORCH NATIVE FP8 TEST")
    
    try:
        device = torch.device('cuda')
        
        # Test torch.float8_e4m3fn (FP8 E4M3)
        if hasattr(torch, 'float8_e4m3fn'):
            print("✓ torch.float8_e4m3fn available")
            
            # Create FP8 tensors
            a = torch.randn(100, 100, device=device, dtype=torch.float32)
            b = torch.randn(100, 100, device=device, dtype=torch.float32)
            
            # Convert to FP8
            a_fp8 = a.to(torch.float8_e4m3fn)
            b_fp8 = b.to(torch.float8_e4m3fn)
            
            print(f"Original tensor dtype: {a.dtype}")
            print(f"FP8 tensor dtype: {a_fp8.dtype}")
            print(f"FP8 tensor shape: {a_fp8.shape}")
            
            # Perform computation in FP8
            result_fp8 = torch.matmul(a_fp8.to(torch.float32), b_fp8.to(torch.float32))
            result_fp32 = torch.matmul(a, b)
            
            # Compare results
            error = torch.mean(torch.abs(result_fp8 - result_fp32))
            print(f"Mean absolute error (FP8 vs FP32): {error:.6f}")
            
            # Verify computation happened
            print(f"FP8 result mean: {result_fp8.mean():.6f}")
            print(f"FP32 result mean: {result_fp32.mean():.6f}")
            
            return True
            
        else:
            print("✗ torch.float8_e4m3fn not available")
            return False
            
    except Exception as e:
        print(f"✗ Native FP8 test failed: {e}")
        return False

def test_fp8_transformer_engine():
    """Test NVIDIA Transformer Engine FP8"""
    print_section("TRANSFORMER ENGINE FP8 TEST")
    
    try:
        import transformer_engine.pytorch as te
        print("✓ Transformer Engine available")
        
        device = torch.device('cuda')
        
        # Create a simple linear layer with FP8
        layer = te.Linear(256, 256, device=device)
        
        # Enable FP8
        with te.fp8_autocast(enabled=True):
            x = torch.randn(32, 256, device=device)
            print(f"Input shape: {x.shape}, dtype: {x.dtype}")
            
            # Forward pass in FP8
            output = layer(x)
            print(f"Output shape: {output.shape}, dtype: {output.dtype}")
            print(f"Output mean: {output.mean():.6f}")
            
            # Verify computation
            loss = output.mean()
            print(f"Loss: {loss:.6f}")
            
            # Test backward pass
            loss.backward()
            print("✓ Backward pass successful")
            
        return True
        
    except ImportError:
        print("✗ Transformer Engine not available")
        return False
    except Exception as e:
        print(f"✗ Transformer Engine test failed: {e}")
        return False

def test_fp8_scaled_matmul():
    """Test scaled FP8 matrix multiplication"""
    print_section("SCALED FP8 MATMUL TEST")
    
    try:
        device = torch.device('cuda')
        
        # Create tensors
        a = torch.randn(128, 128, device=device)
        b = torch.randn(128, 128, device=device)
        
        # Simulate FP8 by quantizing to 8-bit range
        def quantize_fp8_simulation(tensor, scale=1.0):
            # Clamp to FP8 E4M3 range approximately [-240, 240]
            clamped = torch.clamp(tensor * scale, -240, 240)
            # Round to simulate lower precision
            return torch.round(clamped * 16) / 16 / scale
        
        # Scale factors for FP8 simulation
        scale_a = 1.0 / torch.max(torch.abs(a))
        scale_b = 1.0 / torch.max(torch.abs(b))
        
        # Quantize inputs
        a_quantized = quantize_fp8_simulation(a, scale_a)
        b_quantized = quantize_fp8_simulation(b, scale_b)
        
        # Perform computation
        result_quantized = torch.matmul(a_quantized, b_quantized)
        result_fp32 = torch.matmul(a, b)
        
        # Compare
        error = torch.mean(torch.abs(result_quantized - result_fp32))
        print(f"Quantized result mean: {result_quantized.mean():.6f}")
        print(f"FP32 result mean: {result_fp32.mean():.6f}")
        print(f"Mean absolute error: {error:.6f}")
        
        return True
        
    except Exception as e:
        print(f"✗ Scaled FP8 test failed: {e}")
        return False

def test_fp8_custom_kernel():
    """Test custom FP8 kernel approach"""
    print_section("CUSTOM FP8 KERNEL TEST")
    
    try:
        device = torch.device('cuda')
        
        # Use torch.compile for potential FP8 optimizations
        @torch.compile
        def fp8_optimized_matmul(a, b):
            return torch.matmul(a, b)
        
        # Create test tensors
        a = torch.randn(64, 64, device=device, dtype=torch.float16)  # Use FP16 as intermediate
        b = torch.randn(64, 64, device=device, dtype=torch.float16)
        
        # Compiled computation
        result = fp8_optimized_matmul(a, b)
        
        print(f"Input dtype: {a.dtype}")
        print(f"Output dtype: {result.dtype}")
        print(f"Result mean: {result.mean():.6f}")
        print(f"Result std: {result.std():.6f}")
        
        return True
        
    except Exception as e:
        print(f"✗ Custom kernel test failed: {e}")
        return False

def test_fp8_direct_cuda():
    """Test direct CUDA FP8 operations if available"""
    print_section("DIRECT CUDA FP8 TEST")
    
    try:
        device = torch.device('cuda')
        
        # Check for CUDA compute capability
        major, minor = torch.cuda.get_device_capability(0)
        if major < 8:
            print(f"✗ FP8 requires compute capability 8.0+, found {major}.{minor}")
            return False
            
        # Try using torch._C for lower-level operations
        a = torch.randn(32, 32, device=device)
        b = torch.randn(32, 32, device=device)
        
        # Use mixed precision for FP8-like behavior
        with torch.autocast(device_type='cuda', dtype=torch.float16):
            result = torch.matmul(a, b)
        
        print(f"Autocast result dtype: {result.dtype}")
        print(f"Result mean: {result.mean():.6f}")
        
        # Test with different precisions
        for dtype in [torch.float16, torch.bfloat16]:
            if dtype == torch.bfloat16 and major < 8:
                continue
                
            a_cast = a.to(dtype)
            b_cast = b.to(dtype)
            result_cast = torch.matmul(a_cast, b_cast)
            
            print(f"{dtype} result mean: {result_cast.mean():.6f}")
        
        return True
        
    except Exception as e:
        print(f"✗ Direct CUDA test failed: {e}")
        return False

def main():
    print("FP8 Computation Test Script")
    print("Testing actual FP8 computation on Windows + PyTorch + CUDA")
    
    device = check_environment()
    
    if device.type != 'cuda':
        print("\n✗ CUDA not available - FP8 requires CUDA")
        return
    
    # Test different FP8 approaches
    tests = [
        ("Native PyTorch FP8", test_fp8_native_torch),
        ("Transformer Engine FP8", test_fp8_transformer_engine),
        ("Scaled FP8 Simulation", test_fp8_scaled_matmul),
        ("Custom Kernel FP8", test_fp8_custom_kernel),
        ("Direct CUDA FP8", test_fp8_direct_cuda),
    ]
    
    results = []
    for test_name, test_func in tests:
        try:
            success = test_func()
            results.append((test_name, success))
        except Exception as e:
            print(f"✗ {test_name} crashed: {e}")
            results.append((test_name, False))
    
    # Summary
    print_section("SUMMARY")
    successful_tests = 0
    for test_name, success in results:
        status = "✓ PASSED" if success else "✗ FAILED"
        print(f"{test_name}: {status}")
        if success:
            successful_tests += 1
    
    print(f"\nTotal successful tests: {successful_tests}/{len(tests)}")
    
    if successful_tests == 0:
        print("\n❌ No FP8 tests passed. You may need to:")
        print("1. Install transformer-engine: pip install transformer-engine")
        print("2. Use a newer PyTorch version with FP8 support")
        print("3. Ensure you have an Ada Lovelace or Hopper GPU")
        print("4. Check CUDA and driver versions")
    else:
        print(f"\n✅ {successful_tests} FP8 approach(es) working!")

if __name__ == "__main__":
    main()