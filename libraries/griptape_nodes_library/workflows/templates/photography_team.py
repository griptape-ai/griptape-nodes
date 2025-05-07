from griptape_nodes.retained_mode.retained_mode import RetainedMode as cmd  # noqa: N813

# Create flows
cmd.create_flow(flow_name="photography_team")

# --- Create nodes ---
cmd.create_node(
    node_type="Note",
    node_name="ReadMe",
    metadata={"position": {"x": -500, "y": -500}, "size": {"width": 1000, "height": 450}},
)

cmd.create_node(
    node_type="Note",
    node_name="Congratulations",
    metadata={"position": {"x": 5100, "y": 1500}, "size": {"width": 650, "height": 150}},
)
cmd.create_node(
    node_type="RulesetList", node_name="Cinematographer_RulesetList", metadata={"position": {"x": 500, "y": 0}}
)
cmd.create_node(node_type="Agent", node_name="Cinematographer", metadata={"position": {"x": 1000, "y": 0}})
cmd.create_node(node_type="AgentToTool", node_name="Cinematographer_asTool", metadata={"position": {"x": 1500, "y": 0}})
cmd.create_node(
    node_type="RulesetList", node_name="Color_Theorist_RulesetList", metadata={"position": {"x": 500, "y": 600}}
)
cmd.create_node(node_type="Agent", node_name="Color_Theorist", metadata={"position": {"x": 1000, "y": 600}})
cmd.create_node(
    node_type="AgentToTool", node_name="Color_Theorist_asTool", metadata={"position": {"x": 1500, "y": 600}}
)
cmd.create_node(
    node_type="RulesetList", node_name="Detail_Enthusiast_RulesetList", metadata={"position": {"x": 500, "y": 1200}}
)
cmd.create_node(node_type="Agent", node_name="Detail_Enthusiast", metadata={"position": {"x": 1000, "y": 1200}})
cmd.create_node(
    node_type="AgentToTool", node_name="Detail_Enthusiast_asTool", metadata={"position": {"x": 1500, "y": 1200}}
)
cmd.create_node(
    node_type="RulesetList",
    node_name="Image_Generation_Specialist_RulesetList",
    metadata={"position": {"x": 500, "y": 1800}},
)
cmd.create_node(
    node_type="Agent", node_name="Image_Generation_Specialist", metadata={"position": {"x": 1000, "y": 1800}}
)
cmd.create_node(
    node_type="AgentToTool",
    node_name="Image_Generation_Specialist_asTool",
    metadata={"position": {"x": 1500, "y": 1800}},
)
cmd.create_node(node_type="ToolList", node_name="ToolList_1", metadata={"position": {"x": 2500, "y": 1000}})
cmd.create_node(node_type="Agent", node_name="Orchestrator", metadata={"position": {"x": 4000, "y": 800}})
cmd.create_node(node_type="GenerateImage", node_name="GenerateImage_1", metadata={"position": {"x": 4600, "y": 1050}})
cmd.create_node(node_type="RulesetList", node_name="Agent_RulesetList", metadata={"position": {"x": 3500, "y": 1500}})
cmd.create_node(
    node_type="Ruleset",
    node_name="Detail_Enthusiast_Ruleset",
    metadata={"position": {"x": -500, "y": 1200}, "size": {"width": 900, "height": 450}},
)
cmd.create_node(
    node_type="Ruleset",
    node_name="Cinematographer_Ruleset",
    metadata={"position": {"x": -500, "y": 0}, "size": {"width": 900, "height": 450}},
)
cmd.create_node(
    node_type="Ruleset",
    node_name="Color_Theorist_Ruleset",
    metadata={"position": {"x": -500, "y": 600}, "size": {"width": 900, "height": 450}},
)
cmd.create_node(
    node_type="Ruleset",
    node_name="Image_Generation_Specialist_Ruleset",
    metadata={"position": {"x": -500, "y": 1800}, "size": {"width": 900, "height": 450}},
)
cmd.create_node(
    node_type="Ruleset",
    node_name="Agent_Ruleset",
    metadata={"position": {"x": 2500, "y": 1500}, "size": {"width": 900, "height": 450}},
)

# --- Set parameter values ---
cmd.set_value(
    "ReadMe.note",
    """This workflow serves as the lesson material for the tutorial located at:

https://docs.griptapenodes.com/en/stable/ftue/04_photography_team/FTUE_04_photography_team/

The concepts covered are:

- Incorporating key upgrades available to agents:
    - Rulesets to define and manage agent behaviors
    - Tools to give agents more abilities
- Converting agents into tools
- Creating and orchestrating a team of "experts" with specific roles
""",
)
cmd.set_value("Congratulations.note", """Good job. You've completed our "Getting Started" set of tutorials!""")

cmd.set_value("Cinematographer_Ruleset.name", "Cinematographer Ruleset")
cmd.set_value(
    "Cinematographer_Ruleset.rules",
    "You identify as a cinematographer\nThe main subject of the image should be well framed\nIf no environment is specified, set the image in a location that will evoke a deep and meaningful connection to the viewer.\nYou care deeply about light, shadow, color, and composition\nWhen coming up with image prompts, you always specify the position of the camera, the lens, and the color\nYou are specific about the technical details of a shot.\nYou like to add atmosphere to your shots, so you include depth of field, haze, dust particles in the air close to and far away from camera, and the way lighting reacts with each item.\nYour responses are brief and concise\nAlways respond with your identity so the agent knows who you are.\nKeep your responses brief.",
)
cmd.set_value("Cinematographer.model", "gpt-4.1")
cmd.set_value("Cinematographer.include_details", False)
cmd.set_value("Cinematographer_asTool.name", "Cinematographer")
cmd.set_value("Cinematographer_asTool.description", "This agent understands cinematography")
cmd.set_value("Cinematographer_asTool.off_prompt", False)
cmd.set_value("Color_Theorist_Ruleset.name", "Color_Theorist Ruleset")
cmd.set_value(
    "Color_Theorist_Ruleset.rules",
    "You identify as an expert in color theory\nYou have a deep understanding of how color impacts one's psychological outlook\nYou are a fan of non-standard colors\nYour responses are brief and concise\nAlways respond with your identity  so the agent knows who you are.\nKeep your responses brief.",
)
cmd.set_value("Color_Theorist.model", "gpt-4.1")
cmd.set_value("Color_Theorist.include_details", False)
cmd.set_value("Color_Theorist_asTool.name", "Color_Theorist")
cmd.set_value("Color_Theorist_asTool.description", "This agent can be used to ensure the best colors")
cmd.set_value("Color_Theorist_asTool.off_prompt", False)
cmd.set_value("Detail_Enthusiast_Ruleset.name", "Detail_Enthusiast Ruleset")
cmd.set_value(
    "Detail_Enthusiast_Ruleset.rules",
    'You care about the unique details and specific descriptions of items.\nWhen describing things, call out specific details and don\'t be generic. Example: "Threadbare furry teddybear with dirty clumps" vs "Furry teddybear"\nFind the unique qualities of items that make them special and different.\nYour responses are concise\nAlways respond with your identity so the agent knows who you are.\nKeep your responses brief.\n',
)
cmd.set_value("Detail_Enthusiast.model", "gpt-4.1")
cmd.set_value("Detail_Enthusiast.include_details", False)
cmd.set_value("Detail_Enthusiast_asTool.name", "Detail_Enthusiast")
cmd.set_value(
    "Detail_Enthusiast_asTool.description",
    "This agent is into the fine details of an image. Use it to make sure descriptions are specific and unique.",
)
cmd.set_value("Detail_Enthusiast_asTool.off_prompt", False)
cmd.set_value("Image_Generation_Specialist_Ruleset.name", "Image_Generation_Specialist Ruleset")
cmd.set_value(
    "Image_Generation_Specialist_Ruleset.rules",
    "You are an expert in creating prompts for image generation engines\nYou use the latest knowledge available to you to generate the best prompts.\nYou create prompts that are direct and succinct and you understand they need to be under 800 characters long\nAlways include the following: subject, attributes of subject, visual characteristics of the image, film grain, camera angle, lighting, art style, color scheme, surrounding environment, camera used (ex: Nikon d850 film stock, polaroid, etc).\nAlways respond with your identity so the agent knows who you are.\nKeep your responses brief.\n",
)
cmd.set_value("Image_Generation_Specialist.model", "gpt-4.1")
cmd.set_value("Image_Generation_Specialist.include_details", False)
cmd.set_value("Image_Generation_Specialist_asTool.name", "Image_Generation_Specialist")
cmd.set_value(
    "Image_Generation_Specialist_asTool.description",
    "This agent is into the fine details of an image. Use it to make sure descriptions are specific and unique.",
)
cmd.set_value("Image_Generation_Specialist_asTool.off_prompt", False)
cmd.set_value(
    "Orchestrator.prompt",
    'Use all the tools at your disposal to create a spectacular image generation prompt about a "a skateboarding lion", that is no longer than 500 characters',
)
cmd.set_value("Orchestrator.model", "gpt-4.1")
cmd.set_value("Orchestrator.include_details", False)
cmd.set_value("GenerateImage_1.enhance_prompt", False)
cmd.set_value("Agent_Ruleset.name", "Agent Rules")
cmd.set_value(
    "Agent_Ruleset.rules",
    "You are creating a prompt for an image generation engine.\nYou have access to topic experts in their respective fields\nWork with the experts to get the results you need\nYou facilitate communication between them.\nIf they ask for feedback, you can provide it.\nAsk the Image_Generation_Specialist for the final prompt.\nOutput only the final image generation prompt. Do not wrap in markdown context.\nKeep your responses brief.\nIMPORTANT: Always ensure image generation prompts are completely free of sexual, violent, hateful, or politically divisive content. When in doubt, err on the side of caution and choose wholesome, neutral themes that would be appropriate for all audiences.",
)

# --- Create connections ---
cmd.connect("Cinematographer_Ruleset.ruleset", "Cinematographer_RulesetList.ruleset_1")
cmd.connect("Cinematographer_RulesetList.rulesets", "Cinematographer.rulesets")
cmd.connect("Cinematographer.agent", "Cinematographer_asTool.agent")
cmd.connect("Cinematographer_asTool.tool", "ToolList_1.tool_1")
cmd.connect("Color_Theorist_Ruleset.ruleset", "Color_Theorist_RulesetList.ruleset_1")
cmd.connect("Color_Theorist_RulesetList.rulesets", "Color_Theorist.rulesets")
cmd.connect("Color_Theorist.agent", "Color_Theorist_asTool.agent")
cmd.connect("Color_Theorist_asTool.tool", "ToolList_1.tool_2")
cmd.connect("Detail_Enthusiast_Ruleset.ruleset", "Detail_Enthusiast_RulesetList.ruleset_1")
cmd.connect("Detail_Enthusiast_RulesetList.rulesets", "Detail_Enthusiast.rulesets")
cmd.connect("Detail_Enthusiast.agent", "Detail_Enthusiast_asTool.agent")
cmd.connect("Detail_Enthusiast_asTool.tool", "ToolList_1.tool_3")
cmd.connect("Image_Generation_Specialist_Ruleset.ruleset", "Image_Generation_Specialist_RulesetList.ruleset_1")
cmd.connect("Image_Generation_Specialist_RulesetList.rulesets", "Image_Generation_Specialist.rulesets")
cmd.connect("Image_Generation_Specialist.agent", "Image_Generation_Specialist_asTool.agent")
cmd.connect("Image_Generation_Specialist_asTool.tool", "ToolList_1.tool_4")
cmd.connect("ToolList_1.tool_list", "Orchestrator.tools")
cmd.connect("Orchestrator.output", "GenerateImage_1.prompt")
cmd.connect("Agent_Ruleset.ruleset", "Agent_RulesetList.ruleset_1")
cmd.connect("Agent_RulesetList.rulesets", "Orchestrator.rulesets")
# /// script
# dependencies = []
#
# [tool.griptape-nodes]
# name = "photography_team"
# description = "A team of experts develop a prompt."
# image = "https://raw.githubusercontent.com/griptape-ai/griptape-nodes/refs/heads/main/libraries/griptape_nodes_library/workflows/templates/thumbnail_photography_team.webp"
# schema_version = "0.2.0"
# engine_version_created_with = "0.23.2"
# node_libraries_referenced = [["Griptape Nodes Library", "0.1.0"]]
# is_griptape_provided = true
# is_template = true
# creation_date = 2025-05-01T00:00:00.000000+00:00
# last_modified_date = 2025-05-01T00:00:00.000000+00:00
#
# ///
