from pathlib import Path

import pytest
from dotenv import load_dotenv

from griptape_nodes.bootstrap.workflow_runners.subprocess_workflow_runner import SubprocessWorkflowRunner


def get_libraries_dir() -> Path:
    """Get the path to the libraries directory in the repo root."""
    return Path(__file__).parent.parent.parent / "libraries"


def get_libraries() -> list[Path]:
    """Get all libraries required for testing."""
    libraries_dir = get_libraries_dir()
    return [
        libraries_dir / "griptape_nodes_library" / "griptape_nodes_library.json",
        # TODO: https://github.com/griptape-ai/griptape-nodes/issues/1313
        #       libraries_dir / "griptape_nodes_advanced_media_library" / "griptape_nodes_library.json",
    ]


def get_workflows() -> list[str]:
    """Get all workflows to be tested."""
    libraries_dir = Path(get_libraries_dir())
    workflow_dirs = [
        libraries_dir / "griptape_nodes_library" / "workflows" / "templates",
        # TODO: https://github.com/griptape-ai/griptape-nodes/issues/1313
        #       libraries_dir / "griptape_nodes_advanced_media_library" / "workflows" / "templates",
    ]

    workflows = []
    for d in workflow_dirs:
        for f in d.iterdir():
            if f.is_file() and f.suffix == ".py" and not f.name.startswith("__"):
                workflows.extend([str(f)])
    return workflows


load_dotenv()


@pytest.mark.parametrize("workflow_path", get_workflows())
def test_workflow_runs(workflow_path: str) -> None:
    """Simple test to check if the workflow runs without errors."""
    runner = SubprocessWorkflowRunner(libraries=get_libraries())
    runner.run(workflow_path, workflow_name="main", flow_input={})
