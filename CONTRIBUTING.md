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
    # or
    make install
    ```

    This command reads the `pyproject.toml` file and installs everything needed for development within a `.venv` directory.

## Running the Engine Locally for Development

When developing, you typically want to run the engine using your local source code, not a globally installed version.

**Key Development Commands:**

- **Run the Engine:** Use `uv run` to execute the engine script (`gtn` or `griptape-nodes`) within the virtual environment managed by `uv`.
    ```shell
    uv run gtn
    # or
    uv run griptape-nodes engine
    ```
- **Run Initialization:** To trigger the initial setup prompts (API Key, Workspace Directory) using the local code:
    ```shell
    uv run gtn init
    ```
- **Run Tests:**
    ```shell
    uv run pytest
    # or use the Makefile shortcut
    make test/unit
    ```
- **Check Code (Linting & Formatting):**
    ```shell
    uv run ruff check . && uv run ruff format . --check && uv run pyright
    # or use the Makefile shortcut
    make check
    ```
- **Format Code:**
    ```shell
    uv run ruff format .
    # or use the Makefile shortcut
    make format
    ```
- **Fix Code Automatically (Format + Lint):**
    ```shell
    uv run ruff check . --fix && uv run ruff format .
    # or use the Makefile shortcut
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

1. **Using the Local Nodes Library:** By default, a regularly installed engine looks for node definitions (the `griptape_nodes_library.json`) in a system data directory. For development, you **must** tell the engine (run via `uv run gtn`) to use the library file directly from your cloned repository (`./libraries/griptape_nodes_library/griptape_nodes_library.json`).

    - **How to Override:** Create a configuration file in a location that has higher priority than the default system paths. The simplest location is the **root of your cloned `griptape-nodes` repository**.
    - Create a file named `griptape_nodes_config.json` in the project root.
    - Add the following content:
        ```json
        {
          "app_events": {
            "on_app_initialization_complete": {
              "libraries_to_register": [
                "libraries/griptape_nodes_library/griptape_nodes_library.json",
                "libraries/griptape_nodes_advanced_media_library/griptape_nodes_library.json"
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

1. **Setup:** Ensure you've installed dependencies using `uv sync -p --all-extras` (this includes the `docs` group).

1. **Source Files:** Documentation source files are located in the `/docs` directory in Markdown format. The site structure is defined in `mkdocs.yml` in the project root.

1. **Serving Locally:** To preview your changes live, run the MkDocs development server:

    ```shell
    uv run mkdocs serve
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

1. Check out the `main` branch locally:

    ```shell
    git checkout main
    git pull origin main
    ```

1. Bump the new release version:

    ```shell
    # e.g. bumping 0.8.0 to 0.8.1
    make version/patch
    ```

    or:

    ```shell
    # e.g. bumping 0.8.0 to 0.9.0
    make version/minor
    ```

1. Publish the release (creates and pushes tags to Github):

    ```shell
    make version/publish
    ```

Thank you for contributing!
