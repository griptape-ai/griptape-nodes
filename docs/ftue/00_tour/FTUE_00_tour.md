# Getting Started

You just interacted with a Large Language Model (LLM). If you kept the default settings, you specifically used OpenAI's ChatGPT (GPT-4.1).

While this experience might seem similar to using ChatGPT on the web, the real power comes from using LLMs alongside other components in Griptape Nodes. What you've seen is just one node.  Take another look at the library panel on the left to see all the other nodes available.

We're just getting started—there's so much more to explore!

## What You'll Learn

In this tutorial, you will:

- Launch Griptape Nodes
- Navigate through the landing page to a workflow
- Get familiar with the Griptape Nodes Editor
- Add your first nodes to the workspace
- Learn about which parameters can connect to which
- Run an agent

## Launch Griptape Nodes

To launch Griptape Nodes, open your terminal and run one of the following commands:

```bash
griptape-nodes
```

Or use the shorter version:

```bash
gtn
```

After executing the command, you'll see a link to [https://nodes.griptape.ai](https://nodes.griptape.ai) in your terminal. A browser should automatically open to this address, but if it doesn't, or if you need to re-open the page, you can ctrl-click (or cmd-click on Mac) the link in your terminal. This will either open the Griptape Nodes Editor directly or show you a list of options—if the latter, select "Open in browser."

<p align="center">
  <a href="https://nodes.griptape.ai">
    <img src="../assets/launch_link.png" alt="Griptape Nodes launch link in terminal">
  </a>
</p>

## The Landing Page

When your browser opens, you'll be greeted by the Griptape Nodes landing page. This page displays several template workflows that showcase different things we want to introduce you to.  Once you start saving your own files, they will appear here in order of newest-to-oldest.

<p align="center">
  <img src="../assets/landing_page.png" alt="Griptape Nodes landing page">
</p>

These sample workflows are excellent resources for learning about Griptape Nodes' capabilities, but for now, let's start "from scratch".

## Create a new workflow from scratch

On the landing page, locate and click on the **"Create from scratch"** tile.

<p align="center">
  <img src="../assets/create_from_scratch.png" alt="Create from scratch option">
</p>

This action opens a blank workspace where you can build workflows.

## Get familiar with the Griptape Nodes interface

Once you're in the Workflow Editor, take a moment to familiarize yourself with the interface:

<p align="center">
  <img src="../assets/workspace_interface.png" alt="Griptape Nodes workspace interface">
</p>

### Libraries

The most important area to focus on initially is the left panel, the node library. At the top, you'll find the **Create Nodes** section. This panel houses all the standard nodes that come pre-packaged with Griptape Nodes. Each node serves a specific function. As you become familiar with Griptape Nodes, you'll learn how these nodes work and how to combine them to create powerful automations.

<p align="center">
  <img src="../assets/create_nodes_panel.png" alt="Create Nodes panel" width=250">
</p>

### Workflow Console

On the right hand side, you'll see the workflow console. This serves as a resource for tracking and understanding your workflow's creation and execution. For more technical users, it also displays a command log that corresponds to actions in the Editor. This provides a "watch-it-live" learning experience that can lead to custom Python scripting opportunities. You can minimize this panel if you prefer a cleaner interface while working through these tutorials.  We won't be using the workflow console for now.

<p align="center">
  <img src="../assets/workflow_console.png" alt="Workflow Console" width="300">
</p>

## Adding Nodes to the Workspace

There are three interactive methods to creating nodes (and even more in Retained Mode):

<div style="display: flex; justify-content: space-between; gap: 20px; margin-bottom: 30px;">
  <div style="flex: 1;">
    <p><strong>Drag and Drop</strong>: Click and hold on a node from the left panel, then drag it onto your workspace.</p>
    <p align="center">
      <img src="../assets/create_node_dragDrop.gif" alt="Drag and Drop">
    </p>
    <h4 align="center">Drag and Drop</h4>
  </div>
  
  <div style="flex: 1;">
    <p><strong>Double-Click</strong>: Simply double-click any node in the left panel to automatically place it in the center of your workspace.</p>
    <p align="center">
      <img src="../assets/create_node_dblClick.gif" alt="Double Click">
    </p>
    <h4 align="center">Double Click</h4>
  </div>
  
  <div style="flex: 1;">
    <p><strong>Spacebar</strong>: Pressing spacebar brings up a search field.  You can type to find the node you want, and enter to create it.</p>
    <p align="center">
      <img src="../assets/create_node_spacebar.gif" alt="Spacebar">
    </p>
    <h4 align="center">Spacebar Search</h4>
  </div>
</div>

After adding a node, you can:

- Click and drag to reposition it on the workspace
- Edit it's values and behaviors
- Connect it to other nodes (which we'll cover in just a few moments)

!!! info

    To follow the video exactly, create:

    1. An **Agent** ( agents > Agent )

    1. A **FloatInput** ( number > FloatInput )

    1. A **TextInput** ( text > TextInput )

<p align="center">
  <img src="../assets/nodes_in_workspace.png" alt="Node on the workspace">
</p>

## Connecting Nodes

Try dragging from a port on one node to a port on another. Notice anything unusual?

Some connections won't work because not all parameters are compatible with each other. The TextInput node can connect to several places on the Agent, but the FloatInput won't connect to anything on the Agent.  Don't worry—you haven't made a mistake. The FloatInput was included specifically to demonstrate this compatibility limitation. Not all parameters can connect to each other.

!!! Pro tip "Pro Tip"
    Use the port colors as a visual guide for compatibility. Ports with matching colors can connect to each other.

<p align="center">
  <img src="../assets/connected.png" alt="Node on the workspace">
</p>

## Use an Agent

For now, lets get a clean slate and get a real AI interaction under our belt:

1. Go to the File menu and choose **New**. Don't save any changes.

2. In your new scene, make an Agent any way you prefer, and then type something into the prompt field.

3. Click the play button icon in the top right corner to run the node

    <p align="center">
      <img src="../assets/run_node.png" alt="Run the node" width="200">
    </p>

4. When text appears, read the output.

And that was you interacting with an LLM.  If you haven't changed any settings, it'll have specifically been Open AI's Chat GPT (gpt-4.1).

While that was basically no different than going to chatgpt on the web, what is _going to be very different_ is interacting with LLMs among a lot of other things in Griptape Nodes. That's just one node; take a look again at the library on the left.  There's a lot more fun to come.

## Summary

In this tutorial, you learned how to:

- Launch Griptape Nodes
- Navigate through the landing page to a workflow
- Get familiar with the Griptape Nodes Editor
- Add your first nodes to the workspace
- Learn about which parameters can connect to which
- Run an agent

## Next Up

In the next section: [Prompt an Image](../01_prompt_an_image/FTUE_01_prompt_an_image.md), we'll start in on the good stuff: making images!
