from griptape_nodes.retained_mode.retained_mode import RetainedMode as cmd  # noqa: N813

# Create flows
cmd.create_flow(flow_name="compare_prompts")

# Create nodes
cmd.create_node(
    node_type="CreateImage",
    node_name="basic_image",
    parent_flow_name="compare_prompts",
    specific_library_name="Griptape Nodes Library",
    metadata={
        "position": {"x": 107.96492202742763, "y": -55.43579888547769},
        "library_node_metadata": {
            "category": "Image",
            "description": "Generates images using configurable image drivers",
            "display_name": "Create Image",
        },
        "library": "Griptape Nodes Library",
        "node_type": "CreateImage",
        "category": "Image",
    },
)
cmd.create_node(
    node_type="CreateMultilineText",
    node_name="detail_prompt",
    parent_flow_name="compare_prompts",
    specific_library_name="Griptape Nodes Library",
    metadata={
        "position": {"x": -463.93417356294435, "y": 692.2979917734917},
        "library_node_metadata": {
            "category": "Text",
            "description": "Creates and outputs a multiline text string value",
        },
        "library": "Griptape Nodes Library",
        "node_type": "CreateMultilineText",
        "category": "Text",
    },
)
cmd.create_node(
    node_type="CreateImage",
    node_name="enhanced_prompt_image",
    parent_flow_name="compare_prompts",
    specific_library_name="Griptape Nodes Library",
    metadata={
        "position": {"x": 684.9258723363861, "y": 188.19610223068509},
        "library_node_metadata": {
            "category": "Image",
            "description": "Generates images using configurable image drivers",
            "display_name": "Create Image",
        },
        "library": "Griptape Nodes Library",
        "node_type": "CreateImage",
        "category": "Image",
    },
)
cmd.create_node(
    node_type="RunAgent",
    node_name="bespoke_prompt",
    parent_flow_name="compare_prompts",
    specific_library_name="Griptape Nodes Library",
    metadata={
        "position": {"x": 1409.8628765607764, "y": 190.4887558380392},
        "library_node_metadata": {
            "category": "Agent",
            "description": "Runs a previously created Griptape Agent with new prompts",
            "display_name": "Run Agent",
        },
        "library": "Griptape Nodes Library",
        "node_type": "RunAgent",
        "category": "Agent",
    },
)
cmd.create_node(
    node_type="MergeTexts",
    node_name="assemble_prompt",
    parent_flow_name="compare_prompts",
    specific_library_name="Griptape Nodes Library",
    metadata={
        "position": {"x": 103.72844864946936, "y": 690.5315465254349},
        "library_node_metadata": {
            "category": "Text",
            "description": "Joins multiple text inputs with a configurable separator",
        },
        "library": "Griptape Nodes Library",
        "node_type": "MergeTexts",
        "category": "Text",
    },
)
cmd.create_node(
    node_type="CreateImage",
    node_name="bespoke_prompt_image",
    parent_flow_name="compare_prompts",
    specific_library_name="Griptape Nodes Library",
    metadata={
        "position": {"x": 1972.8647080296168, "y": 189.61388211035484},
        "library_node_metadata": {
            "category": "Image",
            "description": "Generates images using configurable image drivers",
            "display_name": "Create Image",
        },
        "library": "Griptape Nodes Library",
        "node_type": "CreateImage",
        "category": "Image",
    },
)
cmd.create_node(
    node_type="CreateText",
    node_name="basic_prompt",
    parent_flow_name="compare_prompts",
    specific_library_name="Griptape Nodes Library",
    metadata={
        "position": {"x": -502.9081437015589, "y": 307.89197790332713},
        "library_node_metadata": {
            "category": "Text",
            "description": "Creates and outputs a simple string value",
            "display_name": "Create Text",
        },
        "library": "Griptape Nodes Library",
        "node_type": "CreateText",
        "category": "Text",
    },
)

# Set parameter values
cmd.set_value("basic_image.prompt", "A capybara eating with utensils")
cmd.set_value("basic_image.enhance_prompt", False)
cmd.set_value(
    "basic_image.output",
    {
        "type": "ImageArtifact",
        "id": "a1d85e8dfa5745b7a39be55cca4660fb",
        "reference": None,
        "meta": {"model": "dall-e-3", "prompt": "A capybara eating with utensils"},
        "name": "image_artifact_250411205314_ll63.png",
        "value": "",
        "format": "png",
        "width": 1024,
        "height": 1024,
    },
)
cmd.set_value("basic_prompt.text", "A capybara eating with utensils")

# Create connections
cmd.connect("basic_image.exec_out", "enhanced_prompt_image.exec_in")
cmd.connect("detail_prompt.text", "assemble_prompt.input_1")
cmd.connect("enhanced_prompt_image.exec_out", "bespoke_prompt.exec_in")
cmd.connect("bespoke_prompt.exec_out", "bespoke_prompt_image.exec_in")
cmd.connect("bespoke_prompt.output", "bespoke_prompt_image.prompt")
cmd.connect("basic_prompt.text", "assemble_prompt.input_2")
cmd.connect("basic_prompt.text", "enhanced_prompt_image.prompt")
cmd.connect("basic_prompt.text", "basic_image.prompt")
cmd.connect("assemble_prompt.output", "bespoke_prompt.prompt")
# /// script
# dependencies = []
#
# [tool.griptape-nodes]
# name = "compare_prompts"
# description = "Example workflow demonstrating how to compare outputs against three different prompting approaches."
# image = "thumbnail_compare_prompts.jpeg"
# schema_version = "0.1.0"
# engine_version_created_with = "0.14.1"
# node_libraries_referenced = [["Griptape Nodes Library", "0.1.0"]]
#
# ///
