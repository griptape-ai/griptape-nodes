"""Unit tests for MathExpression implicit multiplication preprocessing."""

from griptape_nodes_library.number.math_expression import MathExpression


class TestMathExpressionPreprocessing:
    """Test cases for _preprocess_expression method."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.node = MathExpression("test_node")
        self.preprocess = self.node._preprocess_expression

    # Numbers before parentheses
    def test_number_before_parentheses(self) -> None:
        """Test implicit multiplication: number before parentheses."""
        assert self.preprocess("2(a+b)") == "2*(a+b)"
        assert self.preprocess("2.5(a+b)") == "2.5*(a+b)"
        assert self.preprocess("-2(a+b)") == "-2*(a+b)"
        assert self.preprocess("2 (a+b)") == "2*(a+b)"
        assert self.preprocess("2.5 (a+b)") == "2.5*(a+b)"

    # Variables before parentheses
    def test_variable_before_parentheses(self) -> None:
        """Test implicit multiplication: variable before parentheses."""
        assert self.preprocess("a(b+c)") == "a*(b+c)"
        assert self.preprocess("a (b+c)") == "a*(b+c)"
        assert self.preprocess("x(y+z)") == "x*(y+z)"

    # Closing parentheses before numbers/variables
    def test_closing_parentheses_before_number(self) -> None:
        """Test implicit multiplication: closing parentheses before number."""
        assert self.preprocess("(a+b)2") == "(a+b)*2"
        assert self.preprocess("(a+b) 2") == "(a+b)*2"
        assert self.preprocess("(a+b)2.5") == "(a+b)*2.5"

    def test_closing_parentheses_before_variable(self) -> None:
        """Test implicit multiplication: closing parentheses before variable."""
        assert self.preprocess("(a+b)c") == "(a+b)*c"
        assert self.preprocess("(a+b) c") == "(a+b)*c"

    # Numbers before variables
    def test_number_before_variable(self) -> None:
        """Test implicit multiplication: number before variable."""
        assert self.preprocess("2a") == "2*a"
        assert self.preprocess("2 a") == "2*a"
        assert self.preprocess("2.5a") == "2.5*a"
        assert self.preprocess("-2a") == "-2*a"
        assert self.preprocess("2a + 3b") == "2*a+3*b"

    # Variables before numbers
    def test_variable_before_number(self) -> None:
        """Test implicit multiplication: variable before number."""
        assert self.preprocess("a2") == "a*2"
        assert self.preprocess("a 2") == "a*2"
        assert self.preprocess("a2.5") == "a*2.5"
        assert self.preprocess("a2 + b3") == "a*2+b*3"

    # Adjacent variables
    def test_adjacent_variables(self) -> None:
        """Test implicit multiplication: adjacent variables."""
        assert self.preprocess("ab") == "a*b"
        assert self.preprocess("a b") == "a*b"
        assert self.preprocess("abc") == "a*b*c"
        assert self.preprocess("ab + cd") == "a*b+c*d"
        assert self.preprocess("abcdef") == "a*b*c*d*e*f"

    # Complex expressions
    def test_complex_expressions(self) -> None:
        """Test complex expressions with multiple implicit multiplications."""
        assert self.preprocess("2a(b+c)") == "2*a*(b+c)"
        assert self.preprocess("a(b+c)d") == "a*(b+c)*d"
        assert self.preprocess("2a + 3b(c+d)") == "2*a+3*b*(c+d)"
        assert self.preprocess("a(b+c)(d+e)") == "a*(b+c)*(d+e)"
        assert self.preprocess("2(a+b)(c+d)") == "2*(a+b)*(c+d)"

    # Expressions that should NOT be changed
    def test_explicit_multiplication_unchanged(self) -> None:
        """Test that explicit multiplication is not modified."""
        assert self.preprocess("2*a") == "2*a"
        assert self.preprocess("a*b") == "a*b"
        assert self.preprocess("2*(a+b)") == "2*(a+b)"
        assert self.preprocess("a*(b+c)") == "a*(b+c)"

    # Edge cases
    def test_edge_cases(self) -> None:
        """Test edge cases."""
        # Empty string
        assert self.preprocess("") == ""

        # Single variable
        assert self.preprocess("a") == "a"

        # Single number
        assert self.preprocess("2") == "2"

        # Already has explicit multiplication
        assert self.preprocess("2 * a") == "2*a"
        assert self.preprocess("a * 2") == "a*2"

        # Negative numbers
        assert self.preprocess("-2a") == "-2*a"
        assert self.preprocess("a-2b") == "a-2*b"  # Subtraction, not multiplication
        assert self.preprocess("-2(a+b)") == "-2*(a+b)"

        # Decimal numbers
        assert self.preprocess(".5a") == ".5*a"
        assert self.preprocess("-.5a") == "-.5*a"
        assert self.preprocess("2.5a") == "2.5*a"

    # Function calls (should not be modified)
    def test_function_calls_unchanged(self) -> None:
        """Test that function calls are not modified."""
        assert self.preprocess("sin(a)") == "sin(a)"
        assert self.preprocess("cos(2)") == "cos(2)"
        assert self.preprocess("2*sin(a)") == "2*sin(a)"
        assert self.preprocess("asin(0.5)") == "asin(0.5)"

    # Mixed operations
    def test_mixed_operations(self) -> None:
        """Test expressions with mixed operations."""
        assert self.preprocess("2a + 3b - 4c") == "2*a+3*b-4*c"
        assert self.preprocess("a(b+c) + d(e+f)") == "a*(b+c)+d*(e+f)"
        assert self.preprocess("2a * 3b") == "2*a*3*b"
        assert self.preprocess("a/b + c/d") == "a/b+c/d"  # Division unchanged

    # Parentheses edge cases
    def test_parentheses_edge_cases(self) -> None:
        """Test edge cases with parentheses."""
        assert self.preprocess("(a)(b)") == "(a)*(b)"
        assert self.preprocess("2(a)") == "2*(a)"
        assert self.preprocess("(a)2") == "(a)*2"
        assert self.preprocess("(a)b") == "(a)*b"
        assert self.preprocess("a(b)") == "a*(b)"

    # Long chains
    def test_long_chains(self) -> None:
        """Test long chains of variables."""
        assert self.preprocess("abcdefghij") == "a*b*c*d*e*f*g*h*i*j"
        assert self.preprocess("a1b2c3d4") == "a*1*b*2*c*3*d*4"

    # Spaces handling
    def test_spaces_handling(self) -> None:
        """Test that spaces are handled correctly."""
        assert self.preprocess("2 a") == "2*a"
        assert self.preprocess("a 2") == "a*2"
        assert self.preprocess("a b") == "a*b"
        assert self.preprocess("2 (a+b)") == "2*(a+b)"
        assert self.preprocess("(a+b) 2") == "(a+b)*2"

    # Cleanup of extra asterisks
    def test_cleanup_extra_asterisks(self) -> None:
        """Test cleanup of multiple asterisks."""
        # This tests the cleanup regex that converts *** to *
        # Note: The current implementation might not handle all cases perfectly
        # Would need to test if we accidentally create *** patterns

    # Real-world examples
    def test_real_world_examples(self) -> None:
        """Test real-world mathematical expressions."""
        assert self.preprocess("2a + 3b") == "2*a+3*b"
        assert self.preprocess("a(b+c)") == "a*(b+c)"
        assert self.preprocess("2(a+b)") == "2*(a+b)"
        assert self.preprocess("sin(a) + cos(b)") == "sin(a)+cos(b)"
        assert self.preprocess("2sin(a)") == "2*sin(a)"
        assert self.preprocess("asin(0.5)") == "asin(0.5)"  # Function name, not a*sin
