# Getting started

1. Clone the repository:

   ```shell
   git clone https://github.com/griptape-ai/griptape-nodes.git
   ```

1. Install `uv`: https://docs.astral.sh/uv/getting-started/installation/.

1. Navigate to the project directory:

   ```shell
   cd griptape-nodes
   ```

1. Install the project's dependencies:

   ```shell
   make install
   ```

1. Install the Griptape Nodes Engine:

   Visit [https://nodes.griptape.ai/](https://nodes.griptape.ai/), and follow the instructions to install the Engine locally.

1. Configure the Engine to use the nodes library in this repo.

   By default, the Engine looks for the nodes library set up by the `./install.sh` script:
   https://github.com/griptape-ai/griptape-nodes/blob/24d1fdab898e1617793eeb55b7a5a87c161502ef/install.sh?plain=1#L63-L64
   https://github.com/griptape-ai/griptape-nodes/blob/24d1fdab898e1617793eeb55b7a5a87c161502ef/src/griptape_nodes/retained_mode/managers/settings.py?plain=1#L52-L54

   When developing locally, you must configure the Engine to use the nodes library in this repo:

   1. Create a file `griptape_nodes_config.json` in the root of the cloned repo.
   1. Add the following content to the file:
      ```json
      {
        "app_events": {
          "on_app_initialization_complete": {
            "libraries_to_register": [
              "nodes/griptape_nodes_library.json"
            ]
          }
        }
      }
      ```

1. Run the engine 🚗:

   ```shell
   make run
   ```

   To point your engine at a different instance of the API, set the `GRIPTAPE_NODES_API_BASE_URL` environment variable before running:

   ```shell
   GRIPTAPE_NODES_API_BASE_URL=http://localhost:8001 make run
   ```

1. Navigate to the URL provided in the terminal.

# Make Commands

Review [Makefile](https://github.com/griptape-ai/griptape-nodes/blob/main/Makefile) for all commands.

Check the project (type-check, format, lint):

```shell
make check
```

Format the project:

```shell
make format
```

Automatically fix issues (format, lint):

```shell
make fix
```

Serve the documentation:

```shell
make docs/serve
```

Run unit tests:

```shell
make test/unit
```

Run integration tests:

```shell
make test/integration
```

# Engine Commands

Install the engine using the following command:

```bash
uv tool install .
```

You can now run the `griptape-nodes` command (`gtn` shorthand).

Start the engine:

```
griptape-nodes
```

or

```
griptape-nodes engine
```

Get the current configuration:

```
griptape-nodes config
```
