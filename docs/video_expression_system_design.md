# Video Expression System Design

## Overview

We were designing a system to allow video processing nodes to accept **animated expressions** for their parameters, enabling dynamic effects that change over time during video playback.

## Goals

### Primary Objectives

- Allow numeric parameters in video nodes to accept either **static values** or **FFmpeg expressions**
- Enable real-time animation of video effects (vignette intensity, grain strength, color shifts, etc.)
- Provide a consistent interface across all video processing nodes
- Support the `{duration}` placeholder to automatically use actual video duration

### Use Cases

- **Vignette intensity** that increases over time: `t/{duration}`
- **Center position** that moves in patterns: `sin(t/{duration}*3.14159)`
- **Grain strength** that pulses: `0.5 + 0.5*sin(t/{duration}*6.28318)`
- **Color shifts** that oscillate: `cos(t/{duration}*3.14159)`

## Technical Implementation

### 1. Parameter Type System

```python
# Parameters accept multiple input types
Parameter(
    name="angle",
    type="float",
    input_types=["int", "float", "str"],  # Allow expressions as strings
    tooltip="Can be static value or expression like 't/{duration}'"
)
```

### 2. {duration} Placeholder System

```python
def _process_expression_parameter(self, expression: str, duration: float) -> str:
    """Replace {duration} with actual video duration and wrap in quotes."""
    if not isinstance(expression, str):
        return expression
        
    # Replace {duration} placeholder with actual duration
    processed_expression = expression.replace("{duration}", str(duration))
    
    # Wrap in single quotes for FFmpeg if it contains expressions
    if any(char in processed_expression for char in ['t', 'w', 'h', 'n', 'sin', 'cos', 'random']):
        processed_expression = f"'{processed_expression}'"
        
    return processed_expression
```

### 3. Dynamic UI Management

```python
def after_incoming_connection(self, source_node, source_parameter, target_parameter):
    # Remove slider when expression is connected
    if target_parameter.name in expression_params and type(source_node.get_parameter_value(source_parameter.name)) is str:
        slider_traits = target_parameter.find_elements_by_type(Slider)
        if slider_traits:
            target_parameter.remove_trait(trait_type=slider_traits[0])
        target_parameter.type = "str"  # Change type to string

def after_incoming_connection_removed(self, source_node, source_parameter, target_parameter):
    # Restore slider when expression is disconnected
    if target_parameter.name in expression_params:
        target_parameter.type = "float"  # Change type back to float
```

### 4. FFmpeg Expression Processing

```python
# Convert expressions to proper FFmpeg syntax
if isinstance(center_x, (int, float)):
    x0 = f"w/2+{center_x}*w/2"  # Static pixel position
else:
    x0 = f"w/2+({center_x_expr})*w/2"  # Animated pixel position
```

## Example Expressions

### Time-Based Animations

```bash
t/{duration}                    # Linear ramp 0 to 1
0.1 + (t/{duration})*0.8       # Linear ramp 0.1 to 0.9
(t/{duration})^2               # Ease-in ramp
1 - (1 - t/{duration})^2       # Ease-out ramp
```

### Oscillating Effects

```bash
sin(t/{duration}*3.14159)      # Sine wave (1 cycle)
cos(t/{duration}*6.28318)      # Cosine wave (2 cycles)
0.5 + 0.5*sin(t/{duration}*3.14159)  # Sine wave 0 to 1
```

### Random Effects

```bash
0.1 + 0.8*random(0)           # Static random value
0.1 + 0.8*random(t*100)       # Animated random noise
```

## Challenges Encountered

### 1. UI Complexity

- **Dynamic trait management**: Adding/removing sliders based on connection state
- **Type switching**: Changing parameter types between float and string
- **Default value restoration**: Resetting parameters when expressions are disconnected

### 2. FFmpeg Integration

- **Expression syntax**: Proper quoting and escaping for FFmpeg filters
- **Coordinate conversion**: Converting normalized expressions to pixel positions
- **Parameter validation**: Skipping validation for expression strings

### 3. Error Handling

- **Expression parsing**: Handling malformed FFmpeg expressions
- **Type mismatches**: Managing mixed static/expression parameters
- **Fallback behavior**: Graceful degradation when expressions fail

## Base Class Design

### BaseVideoProcessor Enhancements

```python
class BaseVideoProcessor(ControlNode, ABC):
    def _process_expression_parameter(self, expression: str, duration: float) -> str:
        """Process expressions and replace placeholders."""
        
    def _detect_video_properties(self, input_url: str, ffprobe_path: str) -> tuple[float, tuple[int, int], float]:
        """Detect duration, resolution, framerate for expression processing."""
        
    def _process_video(self, input_url: str, output_path: str, **kwargs) -> None:
        """Add video properties to kwargs for expression processing."""
```

## Node Integration Pattern

### Standard Implementation

```python
class AddVignette(BaseVideoProcessor):
    def _setup_custom_parameters(self):
        # Define parameters with expression support
        angle_parameter = Parameter(
            name="angle",
            input_types=["int", "float", "str"],
            tooltip="Can be expression like 't/{duration}'"
        )
        
    def _build_ffmpeg_command(self, input_url: str, output_path: str, **kwargs):
        # Process expressions for all parameters
        duration = kwargs.get("duration", 0.0)
        angle_expr = self._process_expression_parameter(angle, duration)
        
        # Build filter with processed expressions
        filter_complex = f"vignette=angle={angle_expr}:..."
```

## Benefits vs Complexity Trade-off

### Benefits

- **Rich animation capabilities**: Complex time-based effects
- **Consistent interface**: Same pattern across all video nodes
- **FFmpeg integration**: Leverages powerful expression system
- **User flexibility**: Mix static and animated parameters

### Complexity Costs

- **UI management**: Dynamic trait addition/removal
- **Type handling**: Switching between float and string types
- **Error handling**: Expression validation and fallbacks
- **Maintenance**: More complex codebase with edge cases

## Alternative Approaches

### 1. Dedicated Animation Nodes

Create separate "curve" or "animation" nodes that output expression strings:

```python
class SineWaveNode(DataNode):
    def process(self):
        # Output: "sin(t/4.51*3.14159)"
        self.parameter_output_values["expression"] = f"sin(t/{duration}*{frequency})"
```

### 2. Timeline-Based Animation

Use a timeline interface where users can set keyframes and interpolate between values.

### 3. Preset Animation Patterns

Provide predefined animation patterns (fade in, pulse, oscillate) as dropdown options.

## Conclusion

The expression system provides powerful animation capabilities but significantly increases complexity. For a cleaner, more maintainable codebase, we've decided to revert to static parameters and explore simpler animation approaches in the future.

## Future Considerations

If animation is needed later, consider:

1. **Dedicated animation nodes** that output expression strings
1. **Preset animation patterns** as parameter options
1. **Timeline-based keyframe system** for complex animations
1. **Separate animation layer** that doesn't complicate core video processing
