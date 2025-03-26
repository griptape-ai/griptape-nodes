# Griptape Nodes Engine

## Dependencies

[Install uv](https://docs.astral.sh/uv/getting-started/installation/).

To install dependencies:
`make install`

## To start

To start the flask app:
`make run`

To start the engine using SSE (Server Sent Events) to the remote Griptape Nodes API:
`GRIPTAPE_NODES_API_KEY=<your_key> DEBUG=false uv run griptape-nodes`

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

# Contributing

Review the [CONTRIBUTING.md](CONTRIBUTING.md) file for more information.

# API Documentation

Base URL: `http://127.0.0.1:5000/api`
