# Webcam

## What is it?

The Webcam node allows you to capture images directly from your device's camera. It's perfect for real-time image capture, creating interactive workflows, or incorporating live camera input into your image processing pipelines.

## When would I use it?

Use this node when you want to:

- Capture images from your webcam or camera
- Create real-time image processing workflows
- Build interactive applications with live camera input
- Capture photos for immediate processing
- Create live image analysis or recognition systems
- Build camera-based automation workflows

## How to use it

### Basic Setup

1. Add the Webcam node to your workflow
1. Click the "Capture" button to take a photo
1. The captured image will be available at the "output" parameter

### Parameters

#### Camera Settings

- **camera_index** (0-10, default: 0): Which camera to use (if multiple cameras are available)

- **resolution**: The capture resolution

    - **640x480**: Standard resolution
    - **1280x720**: HD resolution
    - **1920x1080**: Full HD resolution
    - **Custom**: Set custom width and height

- **custom_width** (pixels): Custom width when using "Custom" resolution

- **custom_height** (pixels): Custom height when using "Custom" resolution

#### Capture Settings

- **auto_capture** (boolean, default: false): Automatically capture images at intervals
- **capture_interval** (seconds, default: 1): Interval between automatic captures

### Outputs

- **output**: The captured image from the camera

## Example

A typical webcam workflow:

1. Add the Webcam node to your workflow
1. Set the camera settings:
    - Set camera_index to 0 for the default camera
    - Select "1280x720" resolution for HD quality
1. Click the "Capture" button to take a photo
1. Connect the "output" to DisplayImage to view the captured image
1. Optionally connect to other processing nodes for real-time image processing

## Important Notes

- **Camera Access**: The node requires camera permissions to work
- **Real-time Capture**: Images are captured in real-time when you click "Capture"
- **Multiple Cameras**: Use camera_index to select different cameras if available
- **Resolution Control**: Choose the appropriate resolution for your needs

## Common Issues

- **No Camera Found**: Make sure your camera is connected and not being used by other applications
- **Permission Denied**: Grant camera permissions to the application
- **Poor Quality**: Increase the resolution setting for better image quality
- **Camera Busy**: Close other applications that might be using the camera

## Technical Details

The node uses your device's camera system to:

- Access available cameras
- Capture images at the specified resolution
- Provide real-time image capture capabilities
- Support multiple camera inputs

This provides a powerful way to incorporate live camera input into your image processing workflows.
