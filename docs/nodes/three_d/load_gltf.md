# LoadGLTF

## What is it?

The LoadGLTF is a building block that lets you bring a GLTF file into your workflow. It allows you to load 3D models from various sources to be used and displayed within your project.

## When would I use it?

Use this node when you want to:

- Use a GLTF model from a file
- Pass a GLTF model to other nodes in your workflow
- Display a GLTF model as part of your project
- Create a screenshot of a GLTF model to use as part of your workflow

## How to use it

### Basic Setup

1. Add the LoadGLTF node to your workflow
1. Connect it to a source of GLTF data (file browser, URL, or another node output)

### Parameters

- **gltf**: The GLTF file or URL to load. This can be connected to an output from another node or selected via the file browser.

### Outputs

- **gltf**: The loaded GLTF artifact that can be used by other nodes in your flow.
- **image**: An image snapshot of the loaded GLTF model (available after the model is loaded and a snapshot is saved).

## Important Notes

- The node can load GLTF files from your computer using the file browser.
- Once a GLTF model is loaded, you can save a snapshot of it as an image using the 'Save Snapshot' button (if available in the UI).
- The 'image' output parameter will only be available after a snapshot has been saved.

## Common Issues

- **No Model Showing**: Make sure you have properly connected a GLTF source to this node or selected a valid file.
- **Invalid File Type**: Ensure you are providing a valid GLTF file or URL.
- **Image Output Not Available**: The image output is only generated when explicitly saving a snapshot from the UI. Ensure you have triggered this action.
