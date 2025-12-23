# DescribeImage

## What is it?

The DescribeImage node uses AI to generate textual descriptions of an image you provide it. It leverages vision-capable models to analyze image content and produce detailed descriptions based on your specific prompting instructions.

## When would I use it?

Use this node when you want to:

- Generate textual descriptions of images
- Extract information from visual content
- Create alt text for accessibility purposes
- Analyze the content of photographs, diagrams, or other visual media
- Convert visual information into text format for further processing

## How to use it

### Basic Setup

1. Add the DescribeImage node to your workflow
1. Connect an image source to the "image" input
1. Optionally provide specific instructions in the "prompt" field
1. Run the node to generate a description of the image

!!! info "Be Specific About What You Want"

    When creating your prompt, clearly state the elements you are interested in. For example:

    - For color information, try prompts like "Describe the color palette, the color of light and shadow, the saturation and value"
    - For character details, try "Describe the character's gender, age, clothing, posture, demeanor, and actions"

    The more precise you are with your prompts, the more likely it is you'll get the kind of output you desire.

### Parameters

- **agent**: An optional existing agent configuration to use for image description
- **model**: Select a vision-capable prompt model (or connect a Prompt Model Config). Ignored when **agent** is connected.
- **image**: The image you would like to describe (required)
- **prompt**: Instructions for how you want the image described (defaults to "Describe the image")
- **description_only**: If enabled, returns only the description (no conversation)
- **output_schema**: Optional JSON Schema for structured output. Accepts either a JSON schema object or a JSON string. When connected, **output** switches to JSON.

### Outputs

- **output**: The image description. Returns **text** by default, or **JSON** when **output_schema** is provided.
- **agent**: The agent object used for the description, which can be connected to other nodes

## Example

Imagine you want to get a detailed description of a landscape photograph:

1. Add a DescribeImage node to your workflow
1. Connect an image output from another node to the "image" input
1. In the "prompt" field, type: "Describe this landscape in detail, including colors, features, and mood"
1. Run the node
1. The "output" will contain a detailed description of the landscape image

### Structured Output Example (JSON)

If you want the output in a specific JSON shape:

1. Add a `CreateAgentSchema` node and provide an example JSON object (the shape you want back)
1. Connect `CreateAgentSchema.schema` to `DescribeImage.output_schema`
1. Run `DescribeImage`
1. The `output` will be JSON matching your schema (or the run will fail validation)

## Important Notes

- The node requires a valid Griptape API key set up in your environment as `GT_CLOUD_API_KEY`
- By default, the node uses the `gpt-5.2` model through the Griptape Cloud API
- If no prompt is provided, the default "Describe the image" will be used
- If no image is provided, the output will be "No image provided"
- You can provide your own agent configuration for more customized behavior
- The quality of descriptions depends on the clarity and content of the provided image

## Common Issues

- **Missing API Key**: Ensure your Griptape API key is properly set up as the environment variable
- **No Image Provided**: Make sure you've connected a valid image to the "image" input
- **Poor Description Quality**: Try refining your prompt to be more specific about what aspects of the image you want described
- **Processing Errors**: Very complex images or unusual content might result in less accurate descriptions
