from griptape_nodes.retained_mode.events.arbitrary_python_events import (
    RunArbitraryPythonStringRequest,
    RunArbitraryPythonStringResultFailure,
    RunArbitraryPythonStringResultSuccess,
)
from griptape_nodes.retained_mode.griptape_nodes import GriptapeNodes
from griptape_nodes.retained_mode.managers.arbitrary_code_exec_manager import (
    ArbitraryCodeExecManager,
    strip_ansi_codes,
)


class TestStripAnsiCodes:
    def test_removes_color_codes(self) -> None:
        assert strip_ansi_codes("\x1b[31mred\x1b[0m") == "red"

    def test_plain_text_unchanged(self) -> None:
        assert strip_ansi_codes("hello world") == "hello world"

    def test_empty_string(self) -> None:
        assert strip_ansi_codes("") == ""


class TestArbitraryCodeExecManager:
    def test_stdout_captured_as_output(self) -> None:
        manager = ArbitraryCodeExecManager(GriptapeNodes.EventManager())
        request = RunArbitraryPythonStringRequest(python_string="print('hello')")
        result = manager.on_run_arbitrary_python_string_request(request)

        assert isinstance(result, RunArbitraryPythonStringResultSuccess)
        assert result.python_output == "hello\n"

    def test_no_stdout_returns_empty_string(self) -> None:
        manager = ArbitraryCodeExecManager(GriptapeNodes.EventManager())
        request = RunArbitraryPythonStringRequest(python_string="x = 1 + 1")
        result = manager.on_run_arbitrary_python_string_request(request)

        assert isinstance(result, RunArbitraryPythonStringResultSuccess)
        assert result.python_output == ""

    def test_ansi_codes_stripped_from_stdout(self) -> None:
        manager = ArbitraryCodeExecManager(GriptapeNodes.EventManager())
        ansi_red = "\x1b[31m"
        ansi_reset = "\x1b[0m"
        request = RunArbitraryPythonStringRequest(python_string=f"print('{ansi_red}red{ansi_reset}')")
        result = manager.on_run_arbitrary_python_string_request(request)

        assert isinstance(result, RunArbitraryPythonStringResultSuccess)
        assert result.python_output == "red\n"

    def test_local_variable_captured(self) -> None:
        manager = ArbitraryCodeExecManager(GriptapeNodes.EventManager())
        request = RunArbitraryPythonStringRequest(
            python_string="result = 42",
            local_variable_to_capture="result",
        )
        result = manager.on_run_arbitrary_python_string_request(request)

        assert isinstance(result, RunArbitraryPythonStringResultSuccess)
        assert result.python_output == "42"

    def test_local_variable_capture_ignores_stdout(self) -> None:
        manager = ArbitraryCodeExecManager(GriptapeNodes.EventManager())
        request = RunArbitraryPythonStringRequest(
            python_string="print('ignored')\nresult = 'captured'",
            local_variable_to_capture="result",
        )
        result = manager.on_run_arbitrary_python_string_request(request)

        assert isinstance(result, RunArbitraryPythonStringResultSuccess)
        assert result.python_output == "captured"

    def test_missing_local_variable_returns_failure(self) -> None:
        manager = ArbitraryCodeExecManager(GriptapeNodes.EventManager())
        request = RunArbitraryPythonStringRequest(
            python_string="x = 1",
            local_variable_to_capture="nonexistent",
        )
        result = manager.on_run_arbitrary_python_string_request(request)

        assert isinstance(result, RunArbitraryPythonStringResultFailure)
        assert "nonexistent" in result.python_output

    def test_exec_exception_returns_failure(self) -> None:
        manager = ArbitraryCodeExecManager(GriptapeNodes.EventManager())
        request = RunArbitraryPythonStringRequest(python_string="raise ValueError('boom')")
        result = manager.on_run_arbitrary_python_string_request(request)

        assert isinstance(result, RunArbitraryPythonStringResultFailure)
        assert "ERROR:" in result.python_output
        assert "boom" in result.python_output

    def test_syntax_error_returns_failure(self) -> None:
        manager = ArbitraryCodeExecManager(GriptapeNodes.EventManager())
        request = RunArbitraryPythonStringRequest(python_string="def bad(: pass")
        result = manager.on_run_arbitrary_python_string_request(request)

        assert isinstance(result, RunArbitraryPythonStringResultFailure)
        assert "ERROR:" in result.python_output

    def test_recursive_function_works(self) -> None:
        manager = ArbitraryCodeExecManager(GriptapeNodes.EventManager())
        code = "def fact(n): return 1 if n <= 1 else n * fact(n - 1)\nresult = fact(5)"
        request = RunArbitraryPythonStringRequest(
            python_string=code,
            local_variable_to_capture="result",
        )
        result = manager.on_run_arbitrary_python_string_request(request)

        assert isinstance(result, RunArbitraryPythonStringResultSuccess)
        assert result.python_output == "120"

    def test_outer_scope_isolated(self) -> None:
        manager = ArbitraryCodeExecManager(GriptapeNodes.EventManager())
        request = RunArbitraryPythonStringRequest(
            python_string=(
                "try:\n"
                "    _ = manager\n"
                "    result = False\n"
                "except NameError:\n"
                "    result = True"
            ),
            local_variable_to_capture="result",
        )
        result = manager.on_run_arbitrary_python_string_request(request)

        assert isinstance(result, RunArbitraryPythonStringResultSuccess)
        assert result.python_output == "True"
