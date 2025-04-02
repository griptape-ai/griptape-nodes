
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

    # Define what is up here
    def set_min_max(self,value:Any) -> Any:
            pass

    def check_min_max(self,value:Any) -> bool:
            pass
    # If we get this anywhere on a parameter, it is going to grab this guy
    @classmethod
    def get_trait_keys(cls) -> list[str]:
        return ["min","max","minmax", "min_max"]

    def apply_trait_to_parameter(self, parameter: Parameter) -> Parameter:
        # Are there any converters that need to be added?
        def set_min_max(value:Any) -> Any:
            pass
        parameter.converters.append(self.set_min_max)

        # Are there any validators that need to be added?
        def check_min_max(value:Any) -> Any:
            pass
        parameter.validators.append(self.check_min_max)

        return parameter

    def apply_ui_to_parameter(self, parameter: Parameter) -> Parameter:
        # This UI will be silly?? 
        return super().apply_ui_to_parameter(parameter)

# These Traits get added to a list on the parameter. When they are added they apply their functions to the parameter.


class TraitRegistry(SingletonMeta):
    pass