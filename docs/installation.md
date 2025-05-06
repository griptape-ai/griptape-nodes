# Installing Griptape Nodes

An important bit of overview before we begin: Griptape Nodes is actually two things that work together - an Engine and an Editor. The Engine will install and run on your computer, while the Editor is served from the web, and you'll interact with your Engine through a web browser.

> - If you'd rather not install the Engine locally, it is also easy to run it in a hosted environment. The instructions that follow will work the same for either approach.

> - There is no locally-hosted Editor option

There are just 4 easy steps:

1. Sign up or Log in
1. Install Your Engine
1. Configuration
1. Start Your Engine

## 1. Sign up or Log in

To get started, visit [https://griptapenodes.com](https://griptapenodes.com) and click the sign-in button.

![Landing Page](assets/img/getting_started/getting_started-nodes_landing_page.png)

You'll be presented with a Griptape account authorization form.

> If you've already signed up for [Griptape Cloud](https://cloud.griptape.ai), your existing credentials will work here!

![Login](assets/img/getting_started/getting_started-login.png)

Once you've logged in, you'll be presented with a setup screen which walks you through installing the Engine.

## 2. Install Your Engine

1. On the **New Installation** tab, copy the installation command from the first step: **Iinstall Griptape nodes Engine** (it's the bit that starts with `curl`).

1. Open a Terminal on your machine

1. Paste and run the command.

    !!! info

        You can install this on your local machine *or* a cloud-based workstation.

![Installation Page](assets/img/getting_started/getting_started-installation_page.webp)

You'll see this message when installation has completed:

```
**************************************
*      Installation complete!        *
*  Run 'griptape-nodes' (or 'gtn')   *
*      to start the engine.          *
**************************************
```

!!! info

    You'll notice this message gives you two options for commands to run. As previously mentioned, there is no difference between running `griptape-nodes` or `gtn`. They both do the exact same thing.

*After* typing and running `griptape-nodes` or `gtn` in the terminal *for the first time*, you will be asked a series of configuration questions.

## 3. Configuration

**First**, you'll be prompted to set your *workspace directory*. Your workspace directory is where the Griptape Nodes engine will save [project files](./reference/glossary.md#project-files), and [generated assets](./reference/glossary.md#generated-assets). It will also contain a [.env](./reference/glossary.md#.env) for your Griptape Nodes [secret keys](./reference/glossary.md#secret-keys).

```
╭───────────────────────────────────────────────────────────────────╮
│ Workspace Directory                                               │
│     Select the workspace directory. This is the root for your     │
│     projects, saved workflows, and potentially project-specific   │
│     settings. By default, this will be set to                     │
│     "<current_working_directory>/GriptapeNodes", which is the     │
│     directory from which you run the 'gtn' command.               │
│     You may enter a custom directory or press Return to accept    │
│     the default workspace directory.                              │
╰───────────────────────────────────────────────────────────────────╯
Workspace Directory (/Users/user/Documents/local-dev/nodes-test-eng/GriptapeNodes)
```

Pressing Enter will use the default: `<current_working_directory>/GriptapeNodes`, where `<current_working_directory>` is the directory from which you're running the `gtn` command. Alternatively, you can specify any location you prefer.

> You can always return to this dialog using the `gtn init` command if you need to make changes in the future.

**Second**, you'll be prompted for your Griptape Cloud API Key.

1. Return to the web browser and open **Step 3: Generate an API Key**.

1. Click the *Generate API Key* button.

1. Copy that key and enter it in the next step.

![Installation Page wKey hint](assets/img/getting_started/getting_started-installation_page_key_hint.webp)

```
Workspace directory set to: /Users/user/Documents/local-dev/nodes-test-eng/GriptapeNodes
╭─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╮
│ Griptape API Key                                                                                                        │
│         A Griptape API Key is needed to proceed.                                                                        │
│         This key allows the Griptape Nodes Engine to communicate with the Griptape Nodes Editor.                        │
│         In order to get your key, return to the https://nodes.griptape.ai tab in your browser and click the button      │
│         "Generate API Key".                                                                                             │
│         Once the key is generated, copy and paste its value here to proceed.                                            │
╰─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╯
Griptape API Key (YOUR-KEY-HERE):
```

!!! info

    If you've previously run `gtn init` your key might be presented to you in this dialog. You can accept it by pressing Enter or use a different value as required.

## 4. Start Your Engine

You're ready to proceed. Run `griptape-nodes` or `gtn` and return to your browser. Your browser tab at https://nodes.griptape.ai will be updated to an untitled workflow in Griptape Nodes!

![A Blank Griptape_nodes_ editor](assets/img/getting_started/getting_started-blank_editor.png)

Next, on to learning how to actually work inside Griptape Nodes! [Begin](ftue/FTUE.md)
