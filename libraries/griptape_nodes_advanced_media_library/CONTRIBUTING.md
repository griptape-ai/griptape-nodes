# Contributing to Griptape Nodes Advanced Media Library

We welcome contributions to the Griptape Nodes Advanced Media Library! This library provides nodes for advanced machine learning and computer vision tasks, organized by underlying framework.

## Development Location

**IMPORTANT**: For now, all development for this library happens in the main [griptape-nodes](https://github.com/griptape-ai/griptape-nodes) repository under the `libraries/griptape_nodes_advanced_media_library/` directory.

This library is automatically synced to the public [griptape-nodes-library-advanced-media](https://github.com/griptape-ai/griptape-nodes-library-advanced-media) repository when changes are pushed to the `main` branch.

## Development Setup

Please refer to the [main CONTRIBUTING.md](https://github.com/griptape-ai/griptape-nodes/blob/main/CONTRIBUTING.md) in the griptape-nodes repository for:

- Installing `uv` and setting up your development environment
- Installing dependencies with `uv sync --all-groups --all-extras`
- Code style guidelines (Ruff, Pyright)
- Running checks with `make check` and `make fix`
- General contribution workflow

## Contributing Code

1. **Find the library code** - All nodes for this library are located in:

    ```
    libraries/griptape_nodes_advanced_media_library/
    ```

    Nodes are organized by framework/technology:

    - `controlnet_aux/` - ControlNet auxiliary models
    - `diffusers/` - [Diffusers](https://github.com/huggingface/diffusers) package nodes
    - `dino_sam2/` - DINO and SAM2 segmentation models
    - `opencv/` - OpenCV computer vision nodes
    - `openpose/` - OpenPose pose estimation
    - `pillow/` - Pillow image processing
    - `spandrel/` - Spandrel super-resolution
    - `transformers/` - Hugging Face Transformers models
    - `ultralytics/` - YOLO object detection models
    - `artifact_utils/` - Shared utilities for artifacts
    - `utils/` - General utility functions

1. **Make your changes** - Follow the existing code structure and style in the library.

1. **Run tests** - Test the library to ensure your changes work:

    ```shell
    # From the repository root
    uv run pytest libraries/griptape_nodes_advanced_media_library/tests/
    ```

1. **Follow code quality standards** - Run checks before submitting:

    ```shell
    make check  # Check linting, formatting, and type errors
    make fix    # Auto-fix issues where possible
    ```

1. **Submit a pull request** - Open a PR against the `main` branch of the [griptape-nodes](https://github.com/griptape-ai/griptape-nodes) repository.

## Syncing to Public Repository

When changes are merged to the `main` branch in the griptape-nodes repository, they automatically sync to the public [griptape-nodes-library-advanced-media](https://github.com/griptape-ai/griptape-nodes-library-advanced-media) repository via GitHub Actions.

You don't need to do anything special for this sync to happen - it's automatic.

## Making a Release (Maintainers)

Releases involve two steps: updating the version in the main repository, then publishing from the synced library repository.

### Step 1: Update Version (in main griptape-nodes repo)

1. Navigate to the library directory:

    ```shell
    cd libraries/griptape_nodes_advanced_media_library
    ```

1. Edit `griptape_nodes_library.json` and update the version in the metadata section:

    ```json
    {
      "metadata": {
        "library_version": "0.63.1"
      }
    }
    ```

1. Commit and push:

    ```shell
    git add griptape_nodes_library.json
    git commit -m "chore: bump griptape_nodes_advanced_media_library to v0.63.1"
    git push origin main
    ```

    This automatically syncs the changes to the public library repository.

### Step 2: Publish Release (in public library repo)

After the sync completes:

1. Go to the [griptape-nodes-library-advanced-media](https://github.com/griptape-ai/griptape-nodes-library-advanced-media) repository on GitHub
1. Navigate to Actions → "Publish Version"
1. Run the workflow manually to:
    - Create version tag (e.g., `v0.63.1`)
    - Update `stable` tag
    - Create GitHub release with auto-generated notes

The library also has automated workflows:

- `version-bump-patch.yml` / `version-bump-minor.yml` - Can bump versions (but currently versions are managed in main repo)
- `nightly-release.yml` - Creates nightly prerelease builds automatically

## Questions or Issues?

For questions about contributing, please open an issue in the [griptape-nodes](https://github.com/griptape-ai/griptape-nodes) repository.

Thank you for contributing!
