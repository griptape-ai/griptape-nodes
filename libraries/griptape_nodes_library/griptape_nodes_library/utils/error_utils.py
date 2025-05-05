import ast
import re

from griptape.artifacts import BaseArtifact, ErrorArtifact


def get_error_message(error: str) -> str:
    """Get the error message from a string that contains an error code and JSON dictionary."""
    try:
        # Find the JSON dictionary part that starts after "Error code: 401 - "
        match = re.search(r"Error code: \d+ - (\{.*\})", error)
        if match:
            error_dict = match.group(1)
            # ast.literal_eval can safely parse Python literal structures
            error_dict = ast.literal_eval(error_dict)
            if isinstance(error_dict, dict) and "error" in error_dict:
                return error_dict["error"]["message"]
    except (SyntaxError, ValueError, KeyError):
        pass
    return error


def try_throw_error(agent_output: BaseArtifact) -> None:
    """Throws an error if the agent output is an ErrorArtifact."""
    if isinstance(agent_output, ErrorArtifact):
        error_message = get_error_message(agent_output.value)
        msg = f"Agent run failed because of an exception: {error_message}"
        # It wants me to return a TypeError, but this is a runtime error since we're checking for errors that occurred at runtime.
        raise RuntimeError(msg)  # noqa: TRY004
