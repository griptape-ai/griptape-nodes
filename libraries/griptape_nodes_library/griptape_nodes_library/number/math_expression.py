import math
import random
import re
from typing import Any

from asteval import Interpreter  # type: ignore[reportMissingImports]

from griptape_nodes.exe_types.core_types import Parameter, ParameterMode
from griptape_nodes.exe_types.node_types import BaseNode
from griptape_nodes.exe_types.param_types.parameter_int import ParameterInt
from griptape_nodes.exe_types.param_types.parameter_string import ParameterString
from griptape_nodes.traits.options import Options

# All 26 letters of the alphabet for variable names
ALPHABET = "abcdefghijklmnopqrstuvwxyz"

# Constants for variable count limits
DEFAULT_NUM_VARIABLES = 2
MIN_NUM_VARIABLES = 1
MAX_NUM_VARIABLES = 26

# Constants for precision limits
DEFAULT_PRECISION = 6
MIN_PRECISION = 0
MAX_PRECISION = 15


class MathExpression(BaseNode):
    """MathExpression Node that evaluates mathematical expressions with variable inputs."""

    def __init__(self, name: str, metadata: dict[Any, Any] | None = None) -> None:
        super().__init__(name, metadata)

        # Add expression input parameter
        self.add_parameter(
            ParameterString(
                name="expression",
                allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                default_value="a + b",
                tooltip="Mathematical expression to evaluate (e.g., 'a + b * c', 'sin(a) + cos(b)')",
                multiline=False,
                placeholder_text="Enter expression (e.g., a + b * c)",
            )
        )

        # Add number of variables parameter with slider
        self.add_parameter(
            ParameterInt(
                name="num_variables",
                tooltip=f"Number of variables available ({MIN_NUM_VARIABLES}-{MAX_NUM_VARIABLES}, one for each letter a-z)",
                default_value=DEFAULT_NUM_VARIABLES,
                allowed_modes={ParameterMode.PROPERTY},
                slider=True,
                min_val=MIN_NUM_VARIABLES,
                max_val=MAX_NUM_VARIABLES,
            )
        )

        # Add all 26 variable parameters (initially hidden based on num_variables)
        for letter in ALPHABET:
            self.add_parameter(
                Parameter(
                    name=letter,
                    type="float",
                    input_types=["int", "float", "bool"],
                    tooltip=f"Variable {letter.upper()} value",
                    default_value=0,
                    allowed_modes={ParameterMode.INPUT, ParameterMode.PROPERTY},
                    hide=True,  # Initially hidden, will be shown based on num_variables
                )
            )

        # Update visibility based on default num_variables
        self._update_variable_visibility()

        # Add output type parameter
        output_type_choices = ["float", "int"]
        self.add_parameter(
            Parameter(
                name="output_type",
                tooltip="Output type: float or int",
                type="str",
                default_value="float",
                allowed_modes={ParameterMode.PROPERTY},
                traits={Options(choices=output_type_choices)},
            )
        )

        # Add precision parameter (for float output)
        self.add_parameter(
            ParameterInt(
                name="precision",
                tooltip=f"Number of decimal places for float output ({MIN_PRECISION}-{MAX_PRECISION})",
                default_value=DEFAULT_PRECISION,
                allowed_modes={ParameterMode.PROPERTY},
            )
        )

        # Add output parameter (type will be determined by output_type setting)
        self.add_parameter(
            Parameter(
                name="result",
                tooltip="Result of the evaluated expression",
                type="float",
                allowed_modes={ParameterMode.OUTPUT},
                default_value=0.0,
            )
        )

    def _update_variable_visibility(self) -> None:
        """Update visibility of variable parameters based on num_variables setting."""
        num_variables = self._get_num_variables()

        # Show/hide variable parameters based on count
        for i, letter in enumerate(ALPHABET):
            param = self.get_parameter_by_name(letter)
            if param is None:
                continue

            if i < num_variables:
                param.hide = False
            else:
                param.hide = True

    def _get_num_variables(self) -> int:
        """Get and validate the number of variables."""
        num_variables = self.get_parameter_value("num_variables")
        if num_variables is None:
            return DEFAULT_NUM_VARIABLES
        return max(MIN_NUM_VARIABLES, min(MAX_NUM_VARIABLES, int(num_variables)))  # Clamp between MIN and MAX

    def _add_variables_to_interpreter(self, interpreter: Interpreter, num_variables: int) -> None:
        """Add variable values from parameters to the interpreter."""
        for i in range(num_variables):
            letter = ALPHABET[i]
            value = self.get_parameter_value(letter)
            # Handle None, convert to float
            if value is None:
                interpreter.symtable[letter] = 0.0
                continue

            try:
                interpreter.symtable[letter] = float(value)
            except (ValueError, TypeError):
                interpreter.symtable[letter] = 0.0

    def _create_helper_functions(self) -> dict[str, Any]:  # noqa: C901
        """Create helper functions for the interpreter."""

        # Helper function for sum that accepts multiple arguments (unlike Python's built-in sum)
        def sum_multiple_args(*args: float) -> float:
            """Sum function that accepts multiple arguments."""
            if not args:
                return 0.0
            try:
                # Convert all arguments to floats and sum them
                total = 0.0
                for arg in args:
                    total += float(arg)
            except (TypeError, ValueError):
                return 0.0
            else:
                return total

        # Helper function for random number generation with flexible arguments
        def rand_flexible(*args: float) -> float:
            """Random number function: rand() returns 0-1, rand(max) returns 0-max, rand(min, max) returns min-max."""
            max_rand_args = 2
            try:
                if not args:
                    # rand() - return random float between 0 and 1
                    return random.random()  # noqa: S311
                if len(args) == 1:
                    # rand(max) - return random float between 0 and max
                    max_val = float(args[0])
                    return random.uniform(0.0, max_val)  # noqa: S311
                if len(args) == max_rand_args:
                    # rand(min, max) - return random float between min and max
                    min_val = float(args[0])
                    max_val = float(args[1])
                    if min_val > max_val:
                        # Swap if min > max
                        min_val, max_val = max_val, min_val
                    return random.uniform(min_val, max_val)  # noqa: S311
                # Too many arguments, return 0.0
                return 0.0  # noqa: TRY300
            except (TypeError, ValueError):
                return 0.0

        return {"sum": sum_multiple_args, "rand": rand_flexible}

    def _get_math_functions_and_constants(self) -> dict[str, Any]:
        """Get dictionary of math functions and constants."""
        return {
            # Math functions
            "abs": abs,
            "round": round,
            "min": min,
            "max": max,
            "pow": pow,
            "sqrt": math.sqrt,
            "sin": math.sin,
            "cos": math.cos,
            "tan": math.tan,
            "asin": math.asin,
            "acos": math.acos,
            "atan": math.atan,
            "atan2": math.atan2,
            "sinh": math.sinh,
            "cosh": math.cosh,
            "tanh": math.tanh,
            "exp": math.exp,
            "log": math.log,
            "log10": math.log10,
            "log2": math.log2,
            "ceil": math.ceil,
            "floor": math.floor,
            "fabs": math.fabs,
            "fmod": math.fmod,
            "degrees": math.degrees,
            "radians": math.radians,
            # Math constants
            "pi": math.pi,
            "e": math.e,
            "tau": math.tau,
            "inf": float("inf"),
            "nan": float("nan"),
        }

    def _create_interpreter(self) -> Interpreter:
        """Create an asteval interpreter with variables and math functions."""
        interpreter = Interpreter()

        num_variables = self._get_num_variables()
        self._add_variables_to_interpreter(interpreter, num_variables)

        helper_functions = self._create_helper_functions()
        math_functions = self._get_math_functions_and_constants()

        interpreter.symtable.update(helper_functions)
        interpreter.symtable.update(math_functions)

        return interpreter

    def _preprocess_expression(self, expression: str) -> str:
        """Preprocess expression to handle implicit multiplication (e.g., a(b+c) -> a*(b+c)).

        This function inserts explicit * operators where implicit multiplication is expected.
        Handles these cases:
        - Number before parentheses: 2(a+b) -> 2*(a+b)
        - Variable before parentheses: a(b+c) -> a*(b+c)
        - Closing paren before number/variable: (a+b)2 -> (a+b)*2, (a+b)c -> (a+b)*c
        - Number before variable: 2a -> 2*a
        - Variable before number: a2 -> a*2
        - Adjacent variables: ab -> a*b
        """
        if not expression:
            return expression

        # Regex patterns - defined once for clarity
        # Matches numbers: 2, 2.5, -2, -2.5, .5, -.5
        number_pattern = r"-?(?:\d+\.?\d*|\.\d+)"
        # Matches single variable letter (a-z)
        var_pattern = r"[a-z]"
        # Matches either number or variable
        number_or_var = f"({number_pattern}|{var_pattern})"

        # Apply transformations in order of specificity

        # 1. Number before opening parenthesis: 2( -> 2*(, 2.5( -> 2.5*(
        expression = re.sub(rf"({number_pattern})\s*\(", r"\1*(", expression)

        # 2. Variable before opening parenthesis: a( -> a*(
        expression = re.sub(rf"\b({var_pattern})\s*\(", r"\1*(", expression)

        # 3. Closing parenthesis before number or variable: )2 -> )*2, )a -> )*a
        expression = re.sub(rf"\)\s*({number_or_var})\b", r")*\1", expression)
        expression = re.sub(rf"\)({number_or_var})\b", r")*\1", expression)

        # 4. Number before variable: 2a -> 2*a, 2.5a -> 2.5*a
        expression = re.sub(rf"({number_pattern})\s*({var_pattern})\b", r"\1*\2", expression)
        expression = re.sub(rf"({number_pattern})({var_pattern})\b", r"\1*\2", expression)

        # 5. Variable before number: a2 -> a*2, a2.5 -> a*2.5
        expression = re.sub(rf"\b({var_pattern})\s*({number_pattern})\b", r"\1*\2", expression)
        expression = re.sub(rf"\b({var_pattern})({number_pattern})\b", r"\1*\2", expression)

        # 6. Adjacent variables: ab -> a*b, abc -> a*b*c (iterative for chains)
        for _ in range(10):  # Max 10 iterations handles long chains
            new_expr = re.sub(rf"\b({var_pattern})\s*({var_pattern})\b", r"\1*\2", expression)
            new_expr = re.sub(rf"\b({var_pattern})({var_pattern})\b", r"\1*\2", new_expr)
            if new_expr == expression:
                break
            expression = new_expr

        # 7. Cleanup: normalize multiple asterisks and spaces
        expression = re.sub(r"\*\*\*+", "*", expression)  # Multiple * -> single *
        expression = re.sub(r"\s*\*\s*", "*", expression)  # Normalize spaces around *

        return expression

    def _evaluate_expression(self, expression: str) -> float | int:  # noqa: PLR0911
        """Safely evaluate the mathematical expression using asteval."""
        if not expression or not expression.strip():
            return 0.0

        try:
            # Preprocess to handle implicit multiplication
            processed_expr = self._preprocess_expression(expression.strip())
        except (TypeError, ValueError, AttributeError):
            # Return 0.0 on preprocessing error
            return 0.0

        try:
            # Create interpreter with variables and math functions
            interpreter = self._create_interpreter()
        except (TypeError, ValueError, AttributeError):
            # Return 0.0 on interpreter creation error
            return 0.0

        try:
            # Evaluate expression using asteval
            result = interpreter(processed_expr)
        except (TypeError, ValueError, ZeroDivisionError, AttributeError, NameError, SyntaxError):
            # Return 0.0 on evaluation error
            return 0.0

        # Handle None result (asteval returns None for invalid expressions)
        if result is None:
            return 0.0

        # Check if result is numeric (int or float) before converting to float
        # Exclude complex as it cannot be converted to float
        if not isinstance(result, (int, float)):
            return 0.0

        # Convert result to float
        try:
            result = float(result)
        except (TypeError, ValueError):
            return 0.0

        # Get output type and precision settings
        output_type = self.get_parameter_value("output_type") or "float"
        precision = self.get_parameter_value("precision")

        # Handle precision (ensure it's a valid integer between MIN and MAX)
        try:
            precision = int(precision) if precision is not None else DEFAULT_PRECISION
            precision = max(MIN_PRECISION, min(MAX_PRECISION, precision))  # Clamp between MIN and MAX
        except (ValueError, TypeError):
            precision = DEFAULT_PRECISION

        # Format result based on output type
        if output_type == "int":
            # Convert to int (rounds towards zero)
            return int(result)

        # Format as float with specified precision
        # Round to precision decimal places
        rounded = round(float(result), precision)
        return rounded

    def after_value_set(
        self,
        parameter: Parameter,
        value: Any,
    ) -> None:
        # Handle num_variables change - update visibility of variable parameters
        if parameter.name == "num_variables":
            self._update_variable_visibility()

        # Update result when expression, variables, output_type, or precision changes
        num_variables = self._get_num_variables()

        active_variables = set(ALPHABET[:num_variables])
        if (
            parameter.name in ["expression", "output_type", "precision", "num_variables"]
            or parameter.name in active_variables
        ):
            expression = self.get_parameter_value("expression") or ""
            result = self._evaluate_expression(expression)
            self.parameter_output_values["result"] = result
            self.publish_update_to_parameter("result", result)

        return super().after_value_set(parameter, value)

    def process(self) -> None:
        # Get expression and evaluate
        expression = self.get_parameter_value("expression") or ""
        result = self._evaluate_expression(expression)
        self.parameter_output_values["result"] = result
