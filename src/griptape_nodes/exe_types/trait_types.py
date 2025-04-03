
from abc import ABC, abstractmethod
from typing import Any

from griptape_nodes.exe_types.core_types import Parameter
from griptape_nodes.retained_mode.griptape_nodes import SingletonMeta

# Making a new file for parameter traits.

class Trait(ABC):

    @abstractmethod
    @classmethod
    def get_trait_keys(cls) -> list[str]:
        """This will return keys that trigger this trait."""

    @abstractmethod
    def apply_trait_to_parameter(self, parameter:Parameter) -> Parameter:
        # Let's use what we already have. 'Applying a trait' applies converters and validators to a parameter that match the trait that we want.
        pass

    @abstractmethod
    def apply_ui_to_parameter(self, parameter:Parameter) -> Parameter:
        pass


class MinMax(Trait):
    min: Any = 0
    max: Any = 0

    # Helper method for the function
    def set_min_max(self, new_min:Any = None, new_max: Any = None) -> None:
        if new_min:
                self.min = new_min
        if new_max:
                self.max = new_max

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
        # Are there any converters that need to be added?
        parameter.converters.append(self.set_min_max)

        # Are there any validators that need to be added?
        parameter.validators.append(self.check_min_max)

        return parameter
    
    def remove_trait_from_parameter(self, parameter:Parameter) -> Parameter:
         parameter.converters.remove(self.set_min_max)
         parameter.validators.remove(self.check_min_max)

    def apply_ui_to_parameter(self, parameter: Parameter) -> Parameter:
        # What is a good UI thing
        return super().apply_ui_to_parameter(parameter)

# These Traits get added to a list on the parameter. When they are added they apply their functions to the parameter.


class TraitRegistry(SingletonMeta):
    pass