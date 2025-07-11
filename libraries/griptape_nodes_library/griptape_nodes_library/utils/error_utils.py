import ast
import re

import requests
from griptape.artifacts import BaseArtifact, ErrorArtifact


def _parse_griptape_cloud_error_message(error: str) -> str:
    """Griptape Cloud has a quirk where it returns the error message in a format that is not not easily parseable as JSON.

    To workaround this, we must parse the error message to extract the dictionary part.

    TODO: https://github.com/griptape-ai/griptape/issues/1946
    """
    try:
        # Find the JSON dictionary part that starts after "Error code: 401 - "
        match = re.search(r'Error code: \d+ - (\{.*\})"', error)
        if match:
            error_dict = match.group(1)
            # ast.literal_eval can parse strings that aren't perfectly JSON formatted
            error_dict = ast.literal_eval(error_dict)
            if isinstance(error_dict, dict) and "error" in error_dict:
                if "message" in error_dict["error"]:
                    return str(error_dict["error"]["message"])
                return str(error_dict["error"])
            return str(error_dict)
    except (SyntaxError, ValueError, KeyError):
        pass
    return error


def try_throw_error(agent_output: BaseArtifact) -> None:
    """Throws an error if the agent output is an ErrorArtifact."""
    if isinstance(agent_output, ErrorArtifact):
        if isinstance(agent_output.exception, requests.HTTPError):
            if agent_output.exception.response.text:
                error_message = _parse_griptape_cloud_error_message(agent_output.exception.response.text)
            else:
                error_message = str(agent_output.exception)
        else:
            error_message = str(agent_output.value)
        msg = f"Agent run failed because of an exception: {error_message}"
        # It wants me to return a TypeError, but this is a runtime error since we're checking for errors that occurred at runtime.
        raise RuntimeError(msg)  # noqa: TRY004
