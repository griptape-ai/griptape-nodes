from griptape_nodes.retained_mode.retained_mode import RetainedMode as cmd  # noqa: N813

# Create flows
cmd.create_flow(flow_name="compare_prompts")

# --- Create nodes ---
cmd.create_node(
    node_type="Note",
    node_name="ReadMe",
    metadata={"position": {"x": -700, "y": -500}, "size": {"width": 1200, "height": 400}},
)
cmd.create_node(
    node_type="Note",
    node_name="NextStep",
    metadata={"position": {"x": 2400, "y": 650}, "size": {"width": 1100, "height": 200}},
)
cmd.create_node(
    node_type="TextInput",
    node_name="detail_prompt",
    metadata={"position": {"x": -650, "y": 600}, "size": {"width": 650, "height": 330}},
)
cmd.create_node(node_type="TextInput", node_name="basic_prompt", metadata={"position": {"x": -500, "y": 300}})
cmd.create_node(node_type="MergeTexts", node_name="assemble_prompt", metadata={"position": {"x": 100, "y": 600}})
cmd.create_node(node_type="GenerateImage", node_name="basic_image", metadata={"position": {"x": 100, "y": -50}})
cmd.create_node(
    node_type="GenerateImage", node_name="enhanced_prompt_image", metadata={"position": {"x": 700, "y": 200}}
)
cmd.create_node(node_type="Agent", node_name="bespoke_prompt", metadata={"position": {"x": 1300, "y": 200}})
cmd.create_node(
    node_type="GenerateImage", node_name="bespoke_prompt_image", metadata={"position": {"x": 1900, "y": 200}}
)

# --- Set parameter values ---
cmd.set_value(
    "ReadMe.note",
    """This workflow serves as the lesson material for the tutorial located at:

https://docs.griptapenodes.com/en/stable/ftue/03_compare_prompts/FTUE_03_compare_prompts/

The concepts covered are:

- How to use one TextInput node to feed to multiple other inputs
- Different approaches to prompt engineering
- The GenerateImage "Enhance Prompt" feature and how it works behind the scenes
- Comparing the results of different prompting techniques
""",
)
cmd.set_value(
    "NextStep.note",
    """If you're following along with our Getting Started tutorials, check out the next suggested template: Photography_Team.

Load the next tutorial page here:
https://docs.griptapenodes.com/en/stable/ftue/04_photography_team/FTUE_04_photography_team/""",
)
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
cmd.set_value(
    "detail_prompt.text",
    "Enhance the following prompt for an image generation engine. Return only the image generation prompt.\nInclude unique details that make the subject stand out.\nSpecify a specific depth of field, and time of day.\nUse dust in the air to create a sense of depth.\nUse a slight vignetting on the edges of the image.\nUse a color palette that is complementary to the subject.\nFocus on qualities that will make this the most professional looking photo in the world.\n",
)
cmd.set_value("enhanced_prompt_image.prompt", "A capybara eating with utensils")
cmd.set_value("enhanced_prompt_image.enhance_prompt", True)
cmd.set_value("bespoke_prompt.model", "gpt-4.1")
cmd.set_value("bespoke_prompt.include_details", False)
cmd.set_value(
    "assemble_prompt.input_1",
    "Enhance the following prompt for an image generation engine. Return only the image generation prompt.\nInclude unique details that make the subject stand out.\nSpecify a specific depth of field, and time of day.\nUse dust in the air to create a sense of depth.\nUse a slight vignetting on the edges of the image.\nUse a color palette that is complementary to the subject.\nFocus on qualities that will make this the most professional looking photo in the world.\n",
)
cmd.set_value("assemble_prompt.input_2", "A capybara eating with utensils")
cmd.set_value("assemble_prompt.merge_string", "\\n\\n")
cmd.set_value("bespoke_prompt_image.enhance_prompt", False)
cmd.set_value("basic_prompt.text", "A capybara eating with utensils")

# --- Create connections ---
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
# image = "https://raw.githubusercontent.com/griptape-ai/griptape-nodes/refs/heads/main/libraries/griptape_nodes_library/workflows/templates/thumbnail_compare_prompts.webp"
# schema_version = "0.2.0"
# engine_version_created_with = "0.23.2"
# node_libraries_referenced = [["Griptape Nodes Library", "0.1.0"]]
# is_griptape_provided = true
# is_template = true
# creation_date = 2025-05-01T01:00:00.000000+00:00
# last_modified_date = 2025-05-01T01:00:00.000000+00:00
#
# ///
