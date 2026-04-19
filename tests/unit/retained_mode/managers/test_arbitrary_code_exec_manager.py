from griptape_nodes.retained_mode.events.arbitrary_python_events import (
    RunArbitraryPythonStringRequest,
    RunArbitraryPythonStringResultFailure,
    RunArbitraryPythonStringResultSuccess,
)
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes


class TestArbitraryCodeExecManager:
    def test_stdout_captured_as_output(self) -> None:
        """Printed output must be returned as python_output when no variable capture is requested."""
        request = RunArbitraryPythonStringRequest(python_string="print('hello')")
        result = GriptapeNodes.handle_request(request)

        assert isinstance(result, RunArbitraryPythonStringResultSuccess)
        assert result.python_output == "hello\n"

    def test_no_stdout_returns_empty_string(self) -> None:
        """Code that produces no output must yield an empty string, not None or an error."""
        request = RunArbitraryPythonStringRequest(python_string="x = 1 + 1")
        result = GriptapeNodes.handle_request(request)

        assert isinstance(result, RunArbitraryPythonStringResultSuccess)
        assert result.python_output == ""

    def test_ansi_codes_stripped_from_stdout(self) -> None:
        """ANSI codes in printed output must be stripped before returning."""
        ansi_red = "\x1b[31m"
        ansi_reset = "\x1b[0m"
        request = RunArbitraryPythonStringRequest(python_string=f"print('{ansi_red}red{ansi_reset}')")
        result = GriptapeNodes.handle_request(request)

        assert isinstance(result, RunArbitraryPythonStringResultSuccess)
        assert result.python_output == "red\n"

    def test_local_variable_capture_ignores_stdout(self) -> None:
        """When capturing a variable, stdout must be ignored in favour of the captured value."""
        request = RunArbitraryPythonStringRequest(
            python_string="print('ignored')\nresult = 'captured'",
            variable_names_to_capture="result",
        )
        result = GriptapeNodes.handle_request(request)

        assert isinstance(result, RunArbitraryPythonStringResultSuccess)
        assert result.python_output == {"result": "captured"}

    def test_missing_local_variable_returns_failure(self) -> None:
        """Requesting a variable that was never set must return a failure naming the variable."""
        request = RunArbitraryPythonStringRequest(
            python_string="x = 1",
            variable_names_to_capture="nonexistent",
        )
        result = GriptapeNodes.handle_request(request)

        assert isinstance(result, RunArbitraryPythonStringResultFailure)
        assert "nonexistent" in result.python_output

    def test_multiple_missing_variables_all_reported(self) -> None:
        """All missing variable names must appear in the failure message, not just the first one."""
        request = RunArbitraryPythonStringRequest(
            python_string="x = 1",
            variable_names_to_capture=["missing_a", "missing_b"],
        )
        result = GriptapeNodes.handle_request(request)

        assert isinstance(result, RunArbitraryPythonStringResultFailure)
        assert "missing_a" in result.python_output
        assert "missing_b" in result.python_output

    def test_exec_exception_returns_failure(self) -> None:
        """An exception raised during exec must return a failure with the error message."""
        request = RunArbitraryPythonStringRequest(python_string="raise ValueError('boom')")
        result = GriptapeNodes.handle_request(request)

        assert isinstance(result, RunArbitraryPythonStringResultFailure)
        assert "ERROR:" in result.python_output
        assert "boom" in result.python_output

    def test_syntax_error_returns_failure(self) -> None:
        """A syntax error in the submitted code must return a failure, not raise inside the manager."""
        request = RunArbitraryPythonStringRequest(python_string="def bad(: pass")
        result = GriptapeNodes.handle_request(request)

        assert isinstance(result, RunArbitraryPythonStringResultFailure)
        assert "ERROR:" in result.python_output

    def test_recursive_function_works(self) -> None:
        """Recursive functions defined in exec'd code must be able to call themselves."""
        code = "def fact(n): return 1 if n <= 1 else n * fact(n - 1)\nresult = fact(5)"
        request = RunArbitraryPythonStringRequest(
            python_string=code,
            variable_names_to_capture="result",
        )
        result = GriptapeNodes.handle_request(request)

        assert isinstance(result, RunArbitraryPythonStringResultSuccess)
        assert result.python_output == {"result": 120}  # 5!

    def test_outer_scope_isolated(self) -> None:
        """Exec'd code must not be able to access variables from the calling scope."""
        request = RunArbitraryPythonStringRequest(
            python_string=("try:\n    _ = string_buffer\n    result = False\nexcept NameError:\n    result = True"),
            variable_names_to_capture="result",
        )
        result = GriptapeNodes.handle_request(request)

        assert isinstance(result, RunArbitraryPythonStringResultSuccess)
        assert result.python_output == {"result": True}

    def test_multiple_variables_captured_as_dict(self) -> None:
        """Multiple variable names must return a dict mapping each name to its native value."""
        request = RunArbitraryPythonStringRequest(
            python_string="a = 1\nb = 'hello'\nc = [1, 2, 3]",
            variable_names_to_capture=["a", "b", "c"],
        )
        result = GriptapeNodes.handle_request(request)

        assert isinstance(result, RunArbitraryPythonStringResultSuccess)
        assert result.python_output == {"a": 1, "b": "hello", "c": [1, 2, 3]}