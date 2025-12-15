# Contributing to Griptape Nodes

We welcome contributions to the Griptape Nodes project! Whether it's bug fixes, new features, or documentation improvements, your help is appreciated.

## Development Setup

1. **Clone the Repository:**

    ```shell
    git clone https://github.com/griptape-ai/griptape-nodes.git
    cd griptape-nodes
    ```

1. **Install `uv`:**
    If you don't have `uv` installed, follow the official instructions: [Astral's uv Installation Guide](https://docs.astral.sh/uv/getting-started/installation/).

1. **Install Dependencies:**
    Use `uv` to create a virtual environment and install all required dependencies, including base, development, testing, and documentation tools:

    ```shell
    uv sync --all-groups --all-extras
    ```

    Or use the Makefile shortcut:

    ```shell
    make install
    ```

    This command reads the `pyproject.toml` file and installs everything needed for development within a `.venv` directory.

## Running the Engine Locally for Development

When developing, you typically want to run the engine using your local source code, not a globally installed version.

**Key Development Commands:**

- **Run the Engine:** Use `uv run` to execute the engine script (`gtn` or `griptape-nodes`) within the virtual environment managed by `uv`.

    ```shell
    uv run gtn
    ```

    Or use the Makefile shortcut:

    ```shell
    uv run griptape-nodes engine
    ```

- **Run the Engine In Watch Mode:** This command will automatically restart the engine when you make changes to the source code. This is useful for rapid development and testing.

    ```shell
    uv run src/griptape_nodes/app/watch.py
    ```

    Or use the Makefile shortcut:

    ```shell
    make run/watch
    ```

- **Run Initialization:** To trigger the initial setup prompts (API Key, Workspace Directory) using the local code:

    ```shell
    uv run gtn init
    ```

- **Run Unit Tests:**

    ```shell
    uv run pytest test/unit
    ```

    Or use the Makefile shortcut:

    ```shell
    make test/unit
    ```

    > Other test targets (e.g. `tests/integration` and `tests/workflow`) require
    > a `.env` in the repo root with all keys found in `.env.example` to run.

- **Check Code (Linting & Formatting):**

    ```shell
    uv run ruff check . && uv run ruff format . --check && uv run pyright
    ```

    Or use the Makefile shortcut:

    ```shell
    make check
    ```

- **Format Code:**

    ```shell
    uv run ruff format .
    ```

    Or use the Makefile shortcut:

    ```shell
    make format
    ```

- **Fix Code Automatically (Format + Lint):**

    ```shell
    uv run ruff check . --fix && uv run ruff format .
    ```

    Or use the Makefile shortcut:

    ```shell
    make fix
    ```

**Connecting to a Different API Backend:**

> Internal Griptape Developers with access to API project

To point your local engine at a different API instance (e.g., a local Griptape Nodes IDE server), set the `GRIPTAPE_NODES_API_BASE_URL` environment variable:

```shell
GRIPTAPE_NODES_API_BASE_URL=http://localhost:8001 uv run gtn
```

**Connecting to a Different UI**

> Internal Griptape Developers with access to UI project

To point your local engine at a different UI instance (e.g., a local Griptape Nodes UI), set the `GRIPTAPE_NODES_UI_BASE_URL` environment variable:

```shell
GRIPTAPE_NODES_UI_BASE_URL=http://localhost:5173 uv run gtn
```

## Configuration for Development

Griptape Nodes uses a configuration loading system. For full details, see the [Configuration Documentation](docs/configuration.md). Here's what's crucial for development:

1. **`.env` File:** The engine still needs your `GT_CLOUD_API_KEY` to communicate with the Workflow Editor. Ensure this is set in the system-wide environment file located via `gtn init` (typically `~/.config/griptape_nodes/.env`). Running `uv run gtn init` will guide you through creating this if needed.

1. **Using the Local Nodes Library:** By default, a regularly installed engine looks for node definitions (the library config file: `griptape_nodes_library.json` or `griptape-nodes-library.json`) in a system data directory. For development, you **must** tell the engine (run via `uv run gtn`) to use the library file directly from your cloned repository (`./libraries/griptape_nodes_library/griptape_nodes_library.json`).

    - **How to Override:** Create a configuration file in a location that has higher priority than the default system paths. The simplest location is the **root of your cloned `griptape-nodes` repository**.
    - Create a file named `griptape_nodes_config.json` in the project root.
    - Add the following content:
        ```json
        {
          "app_events": {
            "on_app_initialization_complete": {
              "libraries_to_register": [
                "libraries/griptape_nodes_library/griptape_nodes_library.json",
                "libraries/griptape_nodes_advanced_media_library/griptape_nodes_library.json",
                "libraries/griptape_cloud/griptape_nodes_library.json",
              ]
            }
          }
        }
        ```
    - **Why this works:** When you run `uv run gtn` from the project root, the engine's configuration loader finds this `griptape_nodes_config.json` first (due to the "Current Directory & Parents" search path) and uses its `libraries_to_register` setting, overriding the default path.

## Environment Variables

Griptape Nodes uses a variety of environment variables for influencing its low-level behavior.

- **`GRIPTAPE_NODES_API_BASE_URL`**: The base URL for the Griptape Nodes API (default `https://api.nodes.griptape.ai`). This is used to connect the engine to the Workflow Editor.
- **`GT_CLOUD_API_KEY`**: The API key for authenticating with the Griptape Cloud API. This is required for the engine to function properly.
- **`STATIC_SERVER_HOST`**: The host for the static server (default `localhost`). This is used to serve static files from the engine.
- **`STATIC_SERVER_PORT`**: The port for the static server (default `8124`). This is used to serve static files from the engine.
- **`STATIC_SERVER_URL`**: The URL path for the static server (default `/static`). This is used to serve static files from the engine.
- **`STATIC_SERVER_LOG_LEVEL`**: The log level for the static server (default `info`). This is used to control the verbosity of the static server logs.
- **`STATIC_SERVER_ENABLED`**: Whether the static server is enabled (default `true`. This is used to control whether the static server is started or not.

## Contributing to Documentation

The documentation website ([docs.griptapenodes.com](https://docs.griptapenodes.com)) is built using MkDocs with the Material theme.

1. **Setup:** Ensure you've installed dependencies using `make install`.

1. **Source Files:** Documentation source files are located in the `/docs` directory in Markdown format. The site structure is defined in `mkdocs.yml` in the project root.

1. **Serving Locally:** To preview your changes live, first ensure that you have run:

    ```shell
    make install
    ```

    Then run the MkDocs development server:

    ```shell
    uv run mkdocs serve
    ```

    Or use the Makefile shortcut:

    ```shell
    make docs/serve
    ```

This will start a local webserver (usually at `http://127.0.0.1:8000/`). The site will automatically reload when you save changes to the documentation files or `mkdocs.yml`.

1. **Making Changes:** Edit the Markdown files in the `/docs` directory. Add new pages by creating new `.md` files and updating the `nav` section in `mkdocs.yml`.

## Code Style and Quality

- We use **Ruff** for linting and formatting. Please ensure your code conforms to the style by running `make format` or `make fix`.
- We use **Pyright** for static type checking. Run `make check` to ensure there are no type errors.
- Run tests using `make test/unit` or `uv run pytest`.

## Submitting Changes

1. Create a new branch for your feature or bug fix: `git checkout -b my-feature-branch`.
1. Make your changes, commit them with clear messages, and ensure all checks (`make check`) and tests (`make test/unit`) pass.
1. Push your branch to your fork: `git push origin my-feature-branch`.
1. Open a Pull Request (PR) against the `main` branch of the `griptape-ai/griptape-nodes` repository.
1. Clearly describe your changes in the PR description.

## Making a Release (Maintainers)

Griptape Nodes uses [**trunk-based development**](https://trunkbaseddevelopment.com/), where the `main` branch is the primary development branch. There are two types of releases:

- **Regular releases**: Cut from `main` for new features and regular development cycles
- **Patch releases**: Cut from release branches for bug fixes to specific versions

When you publish a regular release, a release branch (e.g., `release/v0.65`) is automatically created. Patch releases are made from these branches.

### Regular Releases (from main)

Use this process for minor and major version bumps that include new features or regular development work:

1. Check out the `main` branch locally:

    ```shell
    git checkout main
    git pull origin main
    ```

1. Bump the version:

    ```shell
    # For patch releases (e.g., 0.65.2 → 0.65.3)
    make version/patch
    ```

    or:

    ```shell
    # For minor releases (e.g., 0.65.0 → 0.66.0)
    make version/minor
    ```

1. Publish the release:

    ```shell
    make version/publish
    ```

    This creates and pushes:

    - A version tag (e.g., `v0.66.0`)
    - An updated `stable` tag
    - A release branch (e.g., `release/v0.66`) for future patch releases

### Patch Releases (from release branches)

Use this process to release bug fixes for a specific version without including newer features from `main`:

1. **Identify the base version** - Find the last stable tag to patch:

    ```shell
    # List recent version tags
    git tag -l 'v*' --sort=-version:refname | head -5
    ```

1. **Create or checkout the release branch** - Release branches follow the pattern `release/v{major.minor}`:

    If the release branch doesn't exist yet, create it from the tag:

    ```shell
    # Example: Creating release/v0.65 from tag v0.65.2
    git checkout -b release/v0.65 v0.65.2
    git push -u origin release/v0.65
    ```

    If the release branch already exists, check it out:

    ```shell
    git checkout release/v0.65
    git pull origin release/v0.65
    ```

1. **Cherry-pick commits from main** - Identify the bug fix commits to backport:

    ```shell
    # View recent commits on main to find the ones you need
    git log main --oneline

    # Cherry-pick specific commits (replace with actual commit hashes)
    git cherry-pick abc123
    git cherry-pick def456
    ```

    If you encounter conflicts, resolve them and continue:

    ```shell
    # After resolving conflicts in your editor
    git add .
    git cherry-pick --continue
    ```

1. **Bump the patch version**:

    ```shell
    make version/patch
    ```

    This bumps the version (e.g., `0.65.2` → `0.65.3`) and automatically commits the change.

1. **Publish the patch release**:

    ```shell
    make version/publish
    ```

    This creates and pushes the version tag (e.g., `v0.65.3`) and updates the `stable` tag.

1. **Automatic synchronization** - After you push to the release branch, GitHub Actions automatically:

    - Detects the version bump commit
    - Cherry-picks it back to `main`
    - Creates a PR to keep `main` in sync with the latest version number

### Important Notes

- **Patch releases** should only contain bug fixes and critical updates, not new features
- **Feature changes** should go through regular releases from `main`
- Release branches follow the pattern `release/v{major.minor}` (e.g., `release/v0.65`)
- Version tags follow the format `v{major}.{minor}.{patch}` (e.g., `v0.65.3`)
- The `stable` tag always points to the latest stable release across all versions
- The `version-bump-on-release.yml` GitHub Actions workflow handles automatic version synchronization back to `main`

Thank you for contributing!
