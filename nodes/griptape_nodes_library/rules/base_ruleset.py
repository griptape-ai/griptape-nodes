from griptape.rules import Rule, Ruleset

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode, ParameterUIOptions
from griptape_nodes.exe_types.node_types import DataNode


class RulesetNode(DataNode):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)

        self.add_parameter(
            Parameter(
                name="name",
                input_types=["str"],
                default_value="Behavior",
                tooltip="Add the name for your ruleset here",
                allowed_modes={ParameterMode.PROPERTY, ParameterMode.INPUT},
            )
        )
        self.add_parameter(
            Parameter(
                name="rules",
                input_types=["str"],
                default_value="",
                tooltip="",
                allowed_modes={ParameterMode.PROPERTY, ParameterMode.INPUT},
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
                output_type="Ruleset",
                default_value=None,
                tooltip="",
                allowed_modes={ParameterMode.PROPERTY, ParameterMode.OUTPUT},
            )
        )

    def process(self) -> None:
        params = self.parameter_values
        name = params.get("name", "Behavior")
        raw_rules = params.get("rules", "")
        sep_rules = [Rule(rule) for rule in raw_rules.split("\n")]
        ruleset = Ruleset(name=name, rules=sep_rules)  # was in [], but made type validation bad for austin

        self.parameter_output_values["ruleset"] = ruleset


if __name__ == "__main__":
    RulesetNode(name="RulesetNode_1").process()
