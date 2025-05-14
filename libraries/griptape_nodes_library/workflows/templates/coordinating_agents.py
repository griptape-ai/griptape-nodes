from griptape_nodes.retained_mode.retained_mode import RetainedMode as cmd  # noqa: N813

# Create flows
cmd.create_flow(flow_name="coordinating_agents")

# Create nodes
cmd.create_node(
    node_type="Note",
    node_name="ReadMe",
    metadata={"position": {"x": -550, "y": -400}, "size": {"width": 1000, "height": 350}},
)
cmd.create_node(
    node_type="Note",
    node_name="NextStep",
    metadata={"position": {"x": 1700, "y": 500}, "size": {"width": 1100, "height": 200}},
)
cmd.create_node(
    node_type="Agent",
    node_name="spanish_story",
    specific_library_name="Griptape Nodes Library",
    metadata={
        "library_node_metadata": {
            "category": "Agent",
            "description": "Runs a previously created Griptape Agent with new prompts",
            "display_name": "Run Agent",
        },
        "library": "Griptape Nodes Library",
        "node_type": "Agent",
        "category": "Agent",
        "position": {"x": -535, "y": 0},
    },
)
cmd.create_node(
    node_type="Agent",
    node_name="to_english",
    specific_library_name="Griptape Nodes Library",
    metadata={
        "library_node_metadata": {
            "category": "Agent",
            "description": "Runs a previously created Griptape Agent with new prompts",
            "display_name": "Run Agent",
        },
        "library": "Griptape Nodes Library",
        "node_type": "Agent",
        "category": "Agent",
        "position": {"x": 635, "y": 0},
    },
)
cmd.create_node(
    node_type="MergeTexts",
    node_name="prompt_header",
    specific_library_name="Griptape Nodes Library",
    metadata={
        "library_node_metadata": {
            "category": "Text",
            "description": "Joins multiple text inputs with a configurable separator",
            "display_name": "Merge Texts",
        },
        "library": "Griptape Nodes Library",
        "node_type": "MergeTexts",
        "category": "Text",
        "position": {"x": 40, "y": 200},
    },
)
cmd.create_node(
    node_type="DisplayText",
    node_name="english_story",
    specific_library_name="Griptape Nodes Library",
    metadata={
        "library_node_metadata": {
            "category": "Text",
            "description": "Displays a text or string value",
            "display_name": "Display Text",
        },
        "library": "Griptape Nodes Library",
        "node_type": "DisplayText",
        "category": "Text",
        "position": {"x": 1200, "y": 200},
        "size": {"width": 475, "height": 265},
    },
)

# Set parameter values
cmd.set_value(
    "ReadMe.note",
    """This workflow serves as the lesson material for the tutorial located at:

https://docs.griptapenodes.com/en/stable/ftue/02_coordinating_agents/FTUE_02_coordinating_agents/

The concepts covered are:

- Multi-agent workflows where agents have different "jobs"
- How to use Merge Text nodes to better pass information between agents
- Understanding execution chains to control the order things happen in""",
)
cmd.set_value(
    "NextStep.note",
    """If you're following along with our Getting Started tutorials, check out the next suggested template: Compare_Prompts.

Load the next tutorial page here:
https://docs.griptapenodes.com/en/stable/ftue/03_compare_prompts/FTUE_03_compare_prompts/""",
)
cmd.set_value(
    "spanish_story.agent",
    {
        "type": "Agent",
        "rulesets": [],
        "rules": [],
        "id": "3610082a55f048f6a70755fc5ad5a791",
        "conversation_memory": {
            "type": "ConversationMemory",
            "runs": [
                {
                    "type": "Run",
                    "id": "8151c6b54c184f4fb06a244b8f2614a3",
                    "meta": None,
                    "input": {
                        "type": "TextArtifact",
                        "id": "e98fb473558c465b8eaf202db77884bf",
                        "reference": None,
                        "meta": {},
                        "name": "e98fb473558c465b8eaf202db77884bf",
                        "value": "Write me a 4-line story in Spanish",
                    },
                    "output": {
                        "type": "TextArtifact",
                        "id": "4e8eaa1eeed14a818a13389b181c34fb",
                        "reference": None,
                        "meta": {"is_react_prompt": False},
                        "name": "4e8eaa1eeed14a818a13389b181c34fb",
                        "value": 'Beneath the old oak, a buried key lay,  \nUnlocking a chest from a forgotten day.  \nInside, a note: "The treasure is you,"  \nAnd the seeker smiled, for they knew it was true.',
                    },
                }
            ],
            "meta": {},
            "max_runs": None,
        },
        "conversation_memory_strategy": "per_structure",
        "tasks": [
            {
                "type": "PromptTask",
                "rulesets": [],
                "rules": [],
                "id": "0085d4e037264bcb8eefd7c1ce1d6d87",
                "state": "State.FINISHED",
                "parent_ids": [],
                "child_ids": [],
                "max_meta_memory_entries": 20,
                "context": {},
                "prompt_driver": {
                    "type": "GriptapeCloudPromptDriver",
                    "temperature": 0.1,
                    "max_tokens": None,
                    "stream": True,
                    "extra_params": {},
                    "structured_output_strategy": "native",
                },
                "tools": [],
                "max_subtasks": 20,
            }
        ],
    },
)
cmd.set_value("spanish_story.prompt", "Write me a 4-line story in Spanish")
cmd.set_value(
    "spanish_story.output",
    "Bajo la luna, el río cantó,  \nUn secreto antiguo en su agua dejó.  \nLa niña lo escuchó y empezó a soñar,  \nQue el mundo era suyo, listo para amar.\n",
)
cmd.set_value(
    "to_english.agent",
    {
        "type": "Agent",
        "rulesets": [],
        "rules": [],
        "id": "e954ec3c2831431abfbd789bd278b1c0",
        "conversation_memory": {
            "type": "ConversationMemory",
            "runs": [
                {
                    "type": "Run",
                    "id": "6ea17a0c803a4bacb90c1c07521a1131",
                    "meta": None,
                    "input": {
                        "type": "TextArtifact",
                        "id": "f31d526077e94062a84ae01655b2b6c9",
                        "reference": None,
                        "meta": {},
                        "name": "f31d526077e94062a84ae01655b2b6c9",
                        "value": 'rewrite this in english\n\nBeneath the old oak, a buried key lay,  \nUnlocking a chest from a forgotten day.  \nInside, a note: "The treasure is you,"  \nAnd the seeker smiled, for they knew it was true.',
                    },
                    "output": {
                        "type": "TextArtifact",
                        "id": "2762bd49ac7b4d9790a9cbac1b8ecb58",
                        "reference": None,
                        "meta": {"is_react_prompt": False},
                        "name": "2762bd49ac7b4d9790a9cbac1b8ecb58",
                        "value": 'Bajo el viejo roble, una llave enterrada yacía,  \nAbriendo un cofre de una época olvidada.  \nDentro, una nota: "El tesoro eres tú,"  \nY el buscador sonrió, pues sabía que era verdad.',
                    },
                }
            ],
            "meta": {},
            "max_runs": None,
        },
        "conversation_memory_strategy": "per_structure",
        "tasks": [
            {
                "type": "PromptTask",
                "rulesets": [],
                "rules": [],
                "id": "e6cb8ec1dd6848239afd5d0b1a7abff9",
                "state": "State.FINISHED",
                "parent_ids": [],
                "child_ids": [],
                "max_meta_memory_entries": 20,
                "context": {},
                "prompt_driver": {
                    "type": "GriptapeCloudPromptDriver",
                    "temperature": 0.1,
                    "max_tokens": None,
                    "stream": True,
                    "extra_params": {},
                    "structured_output_strategy": "native",
                },
                "tools": [],
                "max_subtasks": 20,
            }
        ],
    },
)
cmd.set_value(
    "to_english.prompt",
    "rewrite this in english\n\nBajo la luna, el río cantó,  \nUn secreto antiguo en su agua dejó.  \nLa niña lo escuchó y empezó a soñar,  \nQue el mundo era suyo, listo para amar.",
)
cmd.set_value(
    "to_english.output",
    "Beneath the moon, the river sang,  \nAn ancient secret in its waters it rang.  \nThe girl heard it and began to dream,  \nThat the world was hers, ready to gleam.\n",
)
cmd.set_value("prompt_header.input_1", "rewrite this in english")
cmd.set_value(
    "prompt_header.input_2",
    "Bajo la luna, el río cantó,  \nUn secreto antiguo en su agua dejó.  \nLa niña lo escuchó y empezó a soñar,  \nQue el mundo era suyo, listo para amar.\n",
)
cmd.set_value("prompt_header.merge_string", "\n\n")
cmd.set_value(
    "prompt_header.output",
    "rewrite this in english\n\nBajo la luna, el río cantó,  \nUn secreto antiguo en su agua dejó.  \nLa niña lo escuchó y empezó a soñar,  \nQue el mundo era suyo, listo para amar.",
)
cmd.set_value(
    "english_story.text",
    "Beneath the moon, the river sang,  \nAn ancient secret in its waters it rang.  \nThe girl heard it and began to dream,  \nThat the world was hers, ready to gleam.\n",
)

# Create connections
cmd.connect("spanish_story.exec_out", "to_english.exec_in")
cmd.connect("spanish_story.output", "prompt_header.input_2")
cmd.connect("to_english.output", "english_story.text")
cmd.connect("prompt_header.output", "to_english.prompt")
# /// script
# dependencies = []
#
# [tool.griptape-nodes]
# name = "coordinating_agents"
# description = "Multiple agents, with different jobs."
# image = "https://raw.githubusercontent.com/griptape-ai/griptape-nodes/refs/heads/main/libraries/griptape_nodes_library/workflows/templates/thumbnail_coordinating_agents.webp"
# schema_version = "0.1.0"
# engine_version_created_with = "0.14.1"
# node_libraries_referenced = [["Griptape Nodes Library", "0.1.0"]]
# is_griptape_provided = true
# is_template = true
# creation_date = 2025-05-01T02:00:00.000000+00:00
# last_modified_date = 2025-05-01T02:00:00.000000+00:00
#
# ///
