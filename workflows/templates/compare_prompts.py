from griptape_nodes.retained_mode.retained_mode import RetainedMode as cmd  # noqa: N813

# Create flows
cmd.create_flow(flow_name="compare_prompts")

# Create nodes
cmd.create_node(
    node_type="GenerateImage",
    node_name="basic_image",
    parent_flow_name="compare_prompts",
    specific_library_name="Griptape Nodes Library",
    metadata={"position": {"x": 105, "y": -55}},
)
cmd.create_node(
    node_type="TextInput",
    node_name="detail_prompt",
    parent_flow_name="compare_prompts",
    specific_library_name="Griptape Nodes Library",
    metadata={"position": {"x": -460, "y": 690}},
)
cmd.create_node(
    node_type="GenerateImage",
    node_name="enhanced_prompt_image",
    parent_flow_name="compare_prompts",
    specific_library_name="Griptape Nodes Library",
    metadata={
        "position": {"x": 685, "y": 190},
    },
)
cmd.create_node(
    node_type="Agent",
    node_name="bespoke_prompt",
    parent_flow_name="compare_prompts",
    specific_library_name="Griptape Nodes Library",
    metadata={
        "position": {"x": 1410, "y": 190},
    },
)
cmd.create_node(
    node_type="MergeTexts",
    node_name="assemble_prompt",
    parent_flow_name="compare_prompts",
    specific_library_name="Griptape Nodes Library",
    metadata={
        "position": {"x": 105, "y": 690},
    },
)
cmd.create_node(
    node_type="GenerateImage",
    node_name="bespoke_prompt_image",
    parent_flow_name="compare_prompts",
    specific_library_name="Griptape Nodes Library",
    metadata={
        "position": {"x": 1970, "y": 190},
    },
)
cmd.create_node(
    node_type="TextInput",
    node_name="basic_prompt",
    parent_flow_name="compare_prompts",
    specific_library_name="Griptape Nodes Library",
    metadata={
        "position": {"x": -500, "y": 305},
    },
)

# Set parameter values
cmd.set_value("basic_image.prompt", "A capybara eating with utensils")
cmd.set_value("basic_image.enhance_prompt", False)
cmd.set_value("enhanced_prompt_image.enhance_prompt", True)
cmd.set_value("bespoke_prompt_image.enhance_prompt", False)
cmd.set_value("basic_prompt.text", "A capybara eating with utensils")

# Create connections
cmd.connect("basic_image.exec_out", "enhanced_prompt_image.exec_in")
cmd.connect("detail_prompt.text", "assemble_prompt.input_1")
cmd.connect("enhanced_prompt_image.exec_out", "bespoke_prompt.exec_in")
cmd.connect("bespoke_prompt.exec_out", "bespoke_prompt_image.exec_in")
cmd.connect("bespoke_prompt.output", "bespoke_prompt_image.prompt")
cmd.connect("assemble_prompt.output", "bespoke_prompt.prompt")
cmd.connect("basic_prompt.text", "assemble_prompt.input_2")
cmd.connect("basic_prompt.text", "enhanced_prompt_image.prompt")
cmd.connect("basic_prompt.text", "basic_image.prompt")
# /// script
# dependencies = []
#
# [tool.griptape-nodes]
# name = "compare_prompts"
# description = "See how 3 different approaches to prompts affect image generation."
# image = "https://raw.githubusercontent.com/griptape-ai/griptape-nodes/refs/heads/main/workflows/templates/thumbnail_compare_prompts.webp"
# schema_version = "0.1.0"
# engine_version_created_with = "0.14.1"
# node_libraries_referenced = [["Griptape Nodes Library", "0.1.0"]]
# is_griptape_provided = true
# is_template = true
#
# ///
