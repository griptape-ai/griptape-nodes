from griptape_nodes.retained_mode.retained_mode import RetainedMode as cmd  # noqa: N813

# Create flows
cmd.create_flow()

# Create nodes
cmd.create_node(
    node_type="Note",
    node_name="ReadMe",
    metadata={"position": {"x": 0, "y": -400}, "size": {"width": 1000, "height": 350}},
)
cmd.create_node(
    node_type="Note",
    node_name="NextStep",
    metadata={"position": {"x": 500, "y": 450}, "size": {"width": 1000, "height": 200}},
)
cmd.create_node(
    node_type="GenerateImage",
    node_name="GenerateImage_1",
    specific_library_name="Griptape Nodes Library",
    metadata={
        "position": {"x": 0, "y": 0},
        "library_node_metadata": {
            "category": "Image",
            "description": "Generates images using configurable image drivers",
        },
        "library": "Griptape Nodes Library",
        "node_type": "GenerateImage",
        "category": "Image",
    },
)

# Set parameter values
cmd.set_value(
    "ReadMe.note",
    """This workflow serves as the lesson material for the tutorial located at:

https://docs.griptapenodes.com/en/stable/ftue/01_prompt_an_image/FTUE_01_prompt_an_image/

The concepts covered are:

- Opening saved workflows
- Using text prompts to generate images using the GenerateImage node
- Running entire workflows, or just specific nodes""",
)
cmd.set_value(
    "NextStep.note",
    """If you're following along with our Getting Started tutorials, check out the next workflow: Coordinating Agents.

Load the next tutorial page here:
https://docs.griptapenodes.com/en/stable/ftue/02_coordinating_agents/FTUE_02_coordinating_agents/""",
)
cmd.set_value("GenerateImage_1.prompt", "A potato making an oil painting\n\n")
cmd.set_value("GenerateImage_1.enhance_prompt", True)
cmd.set_value(
    "GenerateImage_1.output",
    {
        "type": "ImageArtifact",
        "id": "89a02c8165d449b1898c1b3abf3e4262",
        "reference": None,
        "meta": {
            "model": "dall-e-3",
            "prompt": "A hyper-realistic close-up of a potato artist meticulously painting an oil masterpiece on a canvas, set in a rustic studio illuminated by the warm, golden light of late afternoon. The potato has a textured, earthy skin with subtle imperfections, and is holding a fine paintbrush with a delicate grip. The canvas features vibrant brushstrokes, hinting at an abstract landscape. Dust particles float gently in the air, catching the sunlight to create a dreamy sense of depth. The background is softly blurred with a shallow depth of field, showcasing wooden easels, jars of paint, and scattered brushes. A slight vignette frames the image, drawing focus to the potato and its artistic endeavor. The color palette is rich and harmonious, with warm browns, deep greens, and golden yellows complementing the potato's natural tones, while pops of crimson and cobalt blue from the painting add visual intrigue.",
        },
        "name": "image_artifact_250412022658_lkwk.png",
        "value": "",
        "format": "png",
        "width": 1024,
        "height": 1024,
    },
)

# Create connections
# /// script
# dependencies = []
#
# [tool.griptape-nodes]
# name = "prompt_an_image"
# description = "The simplest image generation workflow."
# image = "https://raw.githubusercontent.com/griptape-ai/griptape-nodes/refs/heads/main/libraries/griptape_nodes_library/workflows/templates/thumbnail_prompt_an_image.webp"
# schema_version = "0.1.0"
# engine_version_created_with = "0.14.1"
# node_libraries_referenced = [["Griptape Nodes Library", "0.1.0"]]
# is_griptape_provided = true
# is_template = true
# creation_date = 2025-05-01T03:00:00.000000+00:00
# last_modified_date = 2025-05-01T03:00:00.000000+00:00
#
# ///
