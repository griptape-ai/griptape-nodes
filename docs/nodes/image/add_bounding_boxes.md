# AddBoundingBoxes

## What is it?

The AddBoundingBoxes node draws bounding boxes on images from coordinate dictionaries. It's designed to visualize object detection results by overlaying colored rectangles with optional labels on your images. Perfect for displaying YOLO, face detection, or any other detection system outputs.

## When would I use it?

Use this node when you want to:

- Visualize object detection results from YOLO, SSD, or other detection models
- Display face detection bounding boxes with confidence scores
- Annotate images with coordinate-based regions of interest
- Create visual feedback for computer vision workflows
- Debug and verify detection model outputs
- Generate labeled training data visualizations
- Track objects across video frames with labeled boxes
- Combine multiple detection results on a single image

## How to use it

### Basic Setup

1. Add the AddBoundingBoxes node to your workflow
1. Connect an image source to the "input_image" input
1. Connect bounding box data (dict or list of dicts) to the "bounding_boxes" input
1. Optionally customize colors, labels, and thickness
1. The annotated image will be available at the "output" parameter

### Parameters

#### Required Inputs

- **input_image**: The image to draw bounding boxes on (ImageUrlArtifact or ImageArtifact)

- **bounding_boxes**: Single dict or list of dicts containing box coordinates
  - Each dict must have: `x`, `y`, `width`, `height` (integers or convertible strings)
  - Can include additional keys for label templates (e.g., `confidence`, `class`, etc.)
  - Example: `{"x": 100, "y": 50, "width": 200, "height": 150, "confidence": 0.95}`

#### Styling Parameters

- **box_color** (hex color, default: "#FF0000"): Color of the bounding box outlines
  - Uses ColorPicker for easy color selection
  - Supports hex format (e.g., "#FF0000" for red, "#00FF00" for green)

- **line_thickness** (1-10, default: 2): Thickness of the bounding box lines in pixels
  - Lower values for subtle annotations
  - Higher values for bold, prominent boxes

#### Label Parameters

- **show_labels** (boolean, default: True): Toggle label visibility
  - Set to True to show labels above bounding boxes
  - Set to False to hide labels and show only boxes

- **label_key** (string template): Template for bounding box labels
  - Default: `"{x}, {y}, width: {width}, height: {height}"`
  - Use `{key}` syntax to insert values from bounding box dicts
  - Example: `"Class: {class}, Conf: {confidence}"`
  - Example: `"{x}, {y} - Size: {width}x{height}"`
  - Keys not in the dict will remain as `{key}` in the output

### Outputs

- **output**: The image with bounding boxes and labels drawn

## Example

A typical object detection visualization workflow:

1. Load an image using LoadImage
1. Run object detection (e.g., using YOLO or custom detection)
1. Format detection results as dictionaries:
   ```
   [
     {"x": 100, "y": 50, "width": 200, "height": 150, "class": "person", "confidence": 0.95},
     {"x": 350, "y": 120, "width": 180, "height": 200, "class": "car", "confidence": 0.87}
   ]
   ```
1. Connect the image to AddBoundingBoxes "input_image"
1. Connect the detection results to "bounding_boxes"
1. Set label template: `"Class: {class}, Conf: {confidence}"`
1. Choose box color: "#00FF00" (green)
1. Set line thickness: 3 for visibility
1. Connect the "output" to DisplayImage to view the annotated result

## Important Notes

- **Coordinate System**: Bounding boxes use (x, y) as the top-left corner, with width and height extending right and down

- **String Conversion**: The node automatically converts string coordinate values to integers if possible
  - Example: `{"x": "100", "y": "50"}` will work correctly

- **Label Positioning**: Labels are positioned with smart spacing:
  - Default: Above the box with a gap equal to half the label height
  - If near the top of the image: Inside the box at the top

- **Label Size**: Font size automatically scales to 4% of the image height for proportional labeling

- **Validation**: The node validates all inputs before processing:
  - Coordinates must be non-negative (x ≥ 0, y ≥ 0)
  - Dimensions must be positive (width > 0, height > 0)
  - Clear error messages guide you to correct any issues

- **RGBA Support**: The node preserves transparency in RGBA images

## Common Issues

- **Missing Required Keys**: Ensure each bounding box dict has `x`, `y`, `width`, `height`
  - Error message will specify which keys are missing

- **String Coordinates**: If your data has string coordinates, the node will convert them automatically
  - If conversion fails, you'll get a clear error message

- **Negative Coordinates**: Bounding boxes must have non-negative coordinates
  - Check that x ≥ 0 and y ≥ 0

- **Zero or Negative Dimensions**: Width and height must be greater than zero
  - Verify width > 0 and height > 0

- **Labels Not Showing**: Check that:
  - `show_labels` is set to True
  - `label_key` has a valid template
  - The keys in your template exist in your bounding box dicts

- **Label Text Wrong**: Make sure the `{key}` names in your template match the keys in your bounding box dictionaries

## Technical Details

The node performs the following operations:

1. **Input Validation**: 
   - Validates bounding box format (dict or list)
   - Checks for required keys (x, y, width, height)
   - Converts string values to integers if needed
   - Validates coordinate ranges

2. **Color Parsing**: Converts hex color codes to RGB tuples for drawing

3. **Font Loading**: Dynamically loads a font sized at 4% of image height (configurable via `LABEL_HEIGHT_PERCENT` constant)

4. **Box Drawing**: For each bounding box:
   - Calculates rectangle corners from x, y, width, height
   - Draws rectangle outline with specified color and thickness

5. **Label Rendering** (if enabled):
   - Processes template string by replacing `{key}` patterns with values
   - Calculates text dimensions for proper positioning
   - Draws black background rectangle for text visibility
   - Draws white text on the background

6. **Smart Positioning**: Labels are positioned above boxes with proportional spacing, or inside boxes when near the top of the image

The node uses PIL (Pillow) ImageDraw for all rendering operations, ensuring high-quality output compatible with standard image formats.

