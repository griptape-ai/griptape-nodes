from griptape.rules import Rule as gnRule
from griptape.rules import Ruleset as gnRuleset

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode, ParameterUIOptions
from griptape_nodes.exe_types.node_types import DataNode


class RulesetNode(DataNode):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)

        self.add_parameter(
            Parameter(
                name="name",
                input_types=["str"],
                type="str",
                allowed_modes={ParameterMode.PROPERTY, ParameterMode.INPUT},
                default_value="Behavior",
                tooltip="Add the name for your ruleset here",
            )
        )
        self.add_parameter(
            Parameter(
                name="rules",
                input_types=["str"],
                type="str",
                allowed_modes={ParameterMode.PROPERTY, ParameterMode.INPUT},
                default_value="",
                tooltip="",
                ui_options=ParameterUIOptions(
                    string_type_options=ParameterUIOptions.StringType(
                        multiline=True,
                        placeholder_text="Add your rules here, one per line",
                    )
                ),
            )
        )
        self.add_parameter(
            Parameter(
                name="ruleset",
                type="Ruleset",
                output_type="Ruleset",
                allowed_modes={ParameterMode.PROPERTY, ParameterMode.OUTPUT},
                default_value=None,
                tooltip="",
            )
        )

    def process(self) -> None:
        params = self.parameter_values
        name = params.get("name", "Behavior")
        raw_rules = params.get("rules", "")
        sep_rules = [gnRule(rule) for rule in raw_rules.split("\n")]
        ruleset = gnRuleset(name=name, rules=sep_rules)  # was in [], but made type validation bad for austin

        self.parameter_output_values["ruleset"] = ruleset
