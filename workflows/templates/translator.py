from griptape_nodes.retained_mode.retained_mode import RetainedMode as cmd  # noqa: N813

# Create flows
cmd.create_flow(flow_name="translator")

# Create nodes
cmd.create_node(
    node_type="Agent",
    node_name="spanish_story",
    parent_flow_name="translator",
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
        "position": {"x": -535.7908683713299, "y": -7.476151651692973},
    },
)
cmd.create_node(
    node_type="Agent",
    node_name="to_english",
    parent_flow_name="translator",
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
        "position": {"x": 638.5560890213236, "y": -9.073446632293525},
    },
)
cmd.create_node(
    node_type="MergeTexts",
    node_name="prompt_header",
    parent_flow_name="translator",
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
        "position": {"x": 40.84838920453933, "y": 189.99943192938494},
    },
)
cmd.create_node(
    node_type="DisplayText",
    node_name="english_story",
    parent_flow_name="translator",
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
        "position": {"x": 1227.628176549459, "y": 232.41954302364212},
        "size": {"width": 475, "height": 264},
    },
)

# Set parameter values
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
# name = "translator"
# description = "Multiple agents, with different jobs."
# image = "https://raw.githubusercontent.com/griptape-ai/griptape-nodes/refs/heads/main/workflows/templates/thumbnail_translator.webp"
# schema_version = "0.1.0"
# engine_version_created_with = "0.14.1"
# node_libraries_referenced = [["Griptape Nodes Library", "0.1.0"]]
# is_griptape_provided = true
# is_template = true
#
# ///
