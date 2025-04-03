from typing import Any

from griptape_nodes.exe_types.core_types import Parameter, ParameterUIOptions, Trait


class MinMax(Trait):
    min: Any = 10
    max: Any = 30

    # Helper method for the function
    def set_min_max(self, new_min:Any = None, new_max: Any = None) -> None:
        if new_min:
                self.min = new_min
        if new_max:
                self.max = new_max

    def set_parameter_value(self,value:Any) -> Any:
         if value > self.max:
              return self.max
         if value < self.min:
              return self.min
         return value

    def check_min_max(self,parameter:Parameter, value:Any) -> None:
            # i wish i knew what a validator was LOL
            if value > self.max:
                 msg = "Above max lol"
                 raise ValueError(msg)
            if value < self.min:
                 msg = "Below min lol"

    # If we get this anywhere on a parameter, it is going to grab this guy
    @classmethod
    def get_trait_keys(cls) -> list[str]:
        return ["min","max","minmax", "min_max"]

    def apply_trait_to_parameter(self, parameter: Parameter) -> Parameter:
        super().apply_trait_to_parameter(parameter)
        # Are there any converters that need to be added?
        parameter.converters.append(self.set_parameter_value)

        # Are there any validators that need to be added?
        parameter.validators.append(self.check_min_max)

        return parameter

    def remove_trait_from_parameter(self, parameter:Parameter) -> Parameter:
         parameter.converters.remove(self.set_parameter_value)
         parameter.validators.remove(self.check_min_max)
         return parameter

    def apply_ui_to_parameter(self, parameter: Parameter) -> Parameter:
        # What is a good UI thing
        ui_options=ParameterUIOptions(number_type_options=ParameterUIOptions.NumberType(slider=ParameterUIOptions.SliderWidget(min_val=self.min,max_val=self.max)))
        parameter.ui_options = ui_options
        return parameter

# These Traits get added to a list on the parameter. When they are added they apply their functions to the parameter.