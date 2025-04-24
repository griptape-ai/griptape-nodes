# Griptape Nodes

Griptape Nodes provides a powerful, visual, node-based interface for building and executing complex AI workflows. It combines a cloud-based IDE with a locally runnable engine, allowing for easy development, debugging, and execution of Griptape applications.

[![Griptape Nodes Trailer Preview](docs/assets/img/video-thumbnail.jpg)](https://vimeo.com/1064451891)
*(Clicking the image opens the video on Vimeo)*

**Key Features:**

- **Visual Workflow Editor:** Design and connect nodes representing different AI tasks, tools, and logic.
- **Local Engine:** Run workflows securely on your own machine or infrastructure.
- **Debugging & Stepping:** Analyze flow execution step-by-step.
- **Scriptable Interface:** Interact with and control flows programmatically.
- **Extensible:** Build your own custom nodes.

**Learn More:**

- **Full Documentation:** [docs.griptapenodes.com](https://docs.griptapenodes.com)
- **Getting Started:** [docs.griptapenodes.com/setup/](https://docs.griptapenodes.com/en/latest/getting_started/)
- **Engine Configuration:** [docs.griptapenodes.com/configuration/](https://docs.griptapenodes.com/en/latest/configuration/)

______________________________________________________________________

## Quick Installation

Follow these steps to get the Griptape Nodes engine running on your system:

1. **Login:** Visit [Griptape Nodes](https://griptapenodes.com) and log in or sign up using your Griptape Cloud credentials.

1. **Install Command:** Once logged in, you'll find a setup screen. Copy the installation command provided in the "New Installation" section. It will look similar to this (use the **exact** command provided on the website):

    ```bash
    curl -LsSf https://raw.githubusercontent.com/griptape-ai/griptape-nodes/main/install.sh | bash
    ```

1. **Run Installer:** Open a terminal on your machine (local or cloud environment) and paste/run the command. The installer uses `uv` for fast installation; if `uv` isn't present, the script will typically handle installing it.

1. **Initial Configuration (Automatic on First Run):**

    - The first time you run the engine command (`griptape-nodes` or `gtn`), it will guide you through the initial setup:
    - **Workspace Directory:** You'll be prompted to choose a directory where Griptape Nodes will store configurations, project files, secrets (`.env`), and generated assets. You can accept the default (`<current_directory>/GriptapeNodes`) or specify a custom path.
    - **Griptape Cloud API Key:** Return to the [Griptape Nodes setup page](https://griptapenodes.com) in your browser, click "Generate API Key", copy the key, and paste it when prompted in the terminal.

1. **Start the Engine:** After configuration, start the engine by running:

    ```bash
    griptape-nodes
    ```

    *(or the shorter alias `gtn`)*

1. **Connect Workflow Editor:** Refresh the Griptape Nodes Workflow Editor page in your browser. It should now connect to your running engine.

You're now ready to start building flows! For more detailed setup options and troubleshooting, see the full [Setup Guide](https://docs.griptapenodes.com/setup/).
