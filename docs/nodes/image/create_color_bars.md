# CreateColorBars

## What is it?

The CreateColorBars node generates standard color bar test patterns used for video calibration, display testing, and color accuracy verification. It supports over 40 different test patterns including SMPTE, EBU, ARIB standards, as well as various calibration patterns like PLUGE, zone plates, and chroma ramps.

## When would I use it?

Use this node when you want to:

- Calibrate video displays and monitors
- Test color accuracy and brightness levels
- Generate test patterns for video production workflows
- Verify display settings and color space handling
- Create reference images for color grading
- Test video encoding and decoding pipelines
- Generate patterns for display quality assessment

## How to use it

### Basic Setup

1. Add the CreateColorBars node to your workflow
1. Select the type of color bars you want to generate from the "bar_type" dropdown
1. Set the width and height for your test pattern (default: 1920x1080)
1. The generated color bars image will be available at the "image" output

### Parameters

#### Main Settings

- **bar_type**: The type of color bars to generate (string, default: "SMPTE 219-100 Bars")

    Available options include:

    - **SMPTE Patterns**: SMPTE 219-100 Bars, SMPTE 75% Bars, SMPTE Bars, SMPTE 219+i Bars
    - **Full Field Patterns**: 100% Full Field Bars, 75% Full Field Bars, 75% Bars Over Red
    - **International Standards**: EBU Bars (European), ARIB 28-100, ARIB 28-75, ARIB 28+i (Japanese)
    - **HD Patterns**: HD Color Bars
    - **Solid Colors**: Full Field White, Blue, Cyan, Green, Magenta, Red, Yellow
    - **Test Patterns**: Zone Plate, Tartan Bars, Multi Burst, Bowtie
    - **Grayscale Ramps**: Stair 5 Step, Stair 5 Step Vert, Stair 10 Step, Stair 10 Step Vert
    - **Gradient Patterns**: Y Ramp Up, Y Ramp Down, Vertical Ramp
    - **Chroma Patterns**: Legal Chroma Ramp, Full Chroma Ramp, Chroma Ramp
    - **Calibration Patterns**: Pluge (with advanced options), Pathological EG, Pathological PLL
    - **Special Patterns**: AV Delay Pattern 1, AV Delay Pattern 2, Bouncing Box

- **width**: Width of the color bars image in pixels (integer, default: 1920)

- **height**: Height of the color bars image in pixels (integer, default: 1080)

#### PLUGE-Specific Parameters

These parameters are only visible when "Pluge" is selected as the bar_type:

- **pluge_ire_setup**: IRE setup type for PLUGE pattern calibration (string, default: "NTSC 7.5 IRE")

    - **NTSC 7.5 IRE**: Standard NTSC setup level (default)
    - **PAL 0 IRE**: PAL standard with 0 IRE black level
    - **RGB Full Range**: RGB full range (0-255) calibration

- **pluge_bar_count**: Number of PLUGE bars to display (integer, default: 3, range: 2-5)

    - 2 bars: Black level and just above black
    - 3 bars: Super black, black level, and just above black (standard)
    - 4-5 bars: Includes intermediate values between black levels

- **pluge_orientation**: Orientation of PLUGE bars (string, default: "vertical")

    - **vertical**: Bars arranged vertically (default)
    - **horizontal**: Bars arranged horizontally

### Outputs

- **image**: The generated color bars image as an ImageUrlArtifact

## Example

### Basic Color Bars Generation

1. Add a CreateColorBars node to your workflow
1. Select "SMPTE 75% Bars" from the bar_type dropdown
1. Set width to 1920 and height to 1080
1. Connect the "image" output to a DisplayImage node to view the result
1. Optionally connect to SaveImage to save the test pattern

### PLUGE Calibration Pattern

1. Add a CreateColorBars node
1. Select "Pluge" from the bar_type dropdown
1. The PLUGE-specific parameters will automatically appear
1. Configure the calibration:
    - Set pluge_ire_setup to match your video standard (e.g., "NTSC 7.5 IRE" for NTSC, "PAL 0 IRE" for PAL)
    - Set pluge_bar_count to 3 for standard calibration
    - Choose vertical or horizontal orientation
1. Connect the output to DisplayImage to view the calibration pattern

### Custom Resolution Test Pattern

1. Add a CreateColorBars node
1. Select your desired pattern type (e.g., "HD Color Bars")
1. Set custom dimensions:
    - width: 3840 (4K width)
    - height: 2160 (4K height)
1. The pattern will be generated at your specified resolution

## Important Notes

- **Live Preview**: The image is automatically regenerated when you change bar_type, width, height, or PLUGE parameters
- **SMPTE Standards**: SMPTE 75% Bars and SMPTE Bars use 75% intensity levels per SMPTE ECR 1-1978 standard for SDTV
- **IRE Values**: PLUGE patterns use IRE (Institute of Radio Engineers) units for precise black level calibration
- **Real-time Updates**: Changes to parameters trigger immediate regeneration of the color bars
- **PNG Format**: All generated images are saved as PNG files for lossless quality

## Common Use Cases

### Video Production

- Generate SMPTE color bars for broadcast standards compliance
- Create reference patterns for color grading workflows
- Test video encoding pipelines with standard test patterns

### Display Calibration

- Use PLUGE patterns to calibrate black levels and brightness
- Generate zone plates to test display sharpness and focus
- Create grayscale ramps to verify gamma curves

### Quality Testing

- Use pathological patterns to test video processing equipment
- Generate chroma ramps to verify color space handling
- Create multi-burst patterns to test frequency response

## Technical Details

- **Image Format**: PNG (lossless)
- **Color Space**: RGB
- **Default Resolution**: 1920x1080 (Full HD)
- **Standards Supported**: SMPTE, EBU, ARIB
- **IRE Conversion**: IRE values are converted to RGB using the formula: RGB = (IRE / 100) * 255

The node generates industry-standard test patterns suitable for professional video production, broadcast, and display calibration workflows.
