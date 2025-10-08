# Diffusion Pipelines

!!! warning "You need to perform setup steps to use Hugging Face Diffusion Pipeline nodes"

    [This guide](../../how_to/installs/hugging_face.md) will walk you through setting up a Hugging Face account, creating an access token, and installing the required models to make this node fully functional.

## What are they?

The Diffusion Pipeline system consists of two complementary nodes that work together to provide efficient image generation:

- **Diffusion Pipeline Builder**: Builds and caches 🤗 Diffuser Pipelines for reuse across multiple execution nodes
- **Generate Image (Diffusion Pipeline)**: Generates images using the cached pipelines

This modular approach allows you to configure a pipeline once and reuse it multiple times, improving performance and resource efficiency. The system supports a wide range of providers and models through dynamic parameters.

## Supported Providers

The Diffusion Pipeline Builder supports multiple AI model providers:

- **Flux** - High-quality text-to-image generation
- **Qwen** - Multimodal capabilities
- **Stable Diffusion** - Popular open-source diffusion models
- **Allegro** - Video generation capabilities
- **Amused** - Efficient masked image modeling
- **AudioLDM** - Audio generation from text
- **WAN** - Specialized image generation
- **Wuerstchen** - Efficient diffusion architecture
- **Custom** - Support for custom pipeline configurations and self-provided models

## When would I use it?

Use these nodes when you need to:

- Generate images from textual descriptions with various model architectures
- Leverage advanced image generation models for creative projects
- Experiment with different providers and model configurations
- Optimize performance by reusing cached pipelines across multiple generations
- Work with specialized models for audio, video, or multimodal generation

## How to use it

### Basic Setup

The Diffusion Pipeline system uses a two-node workflow:

1. **Configure the Builder**:

    - Add a "Diffusion Pipeline Builder" node to your workflow
    - Select your desired provider (Flux, Stable Diffusion, etc.)
    - Configure provider-specific parameters (model, LoRAs, optimizations)
    - Run the builder to cache the pipeline

1. **Generate Images**:

    - Add a "Generate Image (Diffusion Pipeline)" node
    - Connect the pipeline output from the builder to the runtime node
    - Configure generation parameters (prompt, dimensions, steps, etc.)
    - Run the runtime node to generate images

### Pipeline Builder Parameters

The builder node has dynamic parameters that change based on the selected provider:

- **provider**: Select from supported providers (Flux, Stable Diffusion, etc.)
- **Provider-specific parameters**: Model selection, LoRA configurations, optimization settings
- **pipeline**: Output connection containing the cached pipeline configuration

### Runtime Parameters

The runtime node parameters are dynamically generated based on the connected pipeline:

- **pipeline**: Input connection from the builder node
- **Dynamic generation parameters**: Prompts, dimensions, inference steps, guidance scales
- **output_image**: The generated image as an ImageArtifact
- **seed**: An integer seed for random number generation
- **logs**: Detailed logs of the generation process

!!! note "Dynamic Parameters"

    Both nodes use dynamic parameters that automatically adjust based on your selections. The available parameters will change when you select different providers or connect different pipelines.

### Advanced Features

- **Pipeline Caching**: Built pipelines are cached using configuration hashes for efficient reuse
- **LoRA Support**: Load and configure LoRA adapters for model customization
- **Optimization Options**: Enable various optimizations for better performance
- **Real-time Previews**: Optional intermediate image previews during generation (may slow inference)
- **Connection Preservation**: Runtime node preserves parameter connections when pipeline changes

## Performance Optimization

- **Reuse Pipelines**: Build once, generate many times by connecting multiple runtime nodes to one builder
- **Cache Management**: Pipelines are automatically cached and reused across workflow runs
- **Memory Management**: Configure optimization settings in the builder for your hardware
- **Preview Settings**: Disable intermediate previews for faster generation

## Common Issues

- **Missing API Key**: Ensure the Hugging Face API token is set as `HUGGINGFACE_HUB_ACCESS_TOKEN`; instructions for that are in [this guide](../../how_to/installs/hugging_face.md)
- **Pipeline Not Found**: If you see cache errors, ensure the builder node has been executed successfully
- **Memory Constraints**: Large models or high-resolution generation may require significant GPU memory
- **Provider Compatibility**: Ensure your selected model is compatible with the chosen pipeline type
