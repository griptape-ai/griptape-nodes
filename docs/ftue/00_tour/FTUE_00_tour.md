# Interface Basics

Welcome to Griptape Nodes! This tutorial will guide you through your first step with this powerful tool, creating your first workflow.

## What You'll Learn

In this tutorial, you will:

- Launch Griptape Nodes
- Navigate through the landing page to a workflow
- Get familiar with the Griptape Nodes interface
- Add your first nodes to the workspace
- Connect your nodes into a small workflow

## Launch Griptape Nodes

To begin using Griptape Nodes, open your terminal and run one of the following commands:

```bash
griptape-nodes
```

Or use the shorter version:

```bash
gtn
```

After executing the command, you'll see a link in your terminal. Click on it, and your browser will automatically open to the Griptape Nodes Editor.

<p align="center">
  <img src="../assets/launch_link.png" alt="Griptape Nodes launch link in terminal">
</p>

## The Landing Page

When your browser opens, you'll be greeted by the Griptape Nodes landing page. This page displays several template workflows that showcase different things we want to introduce you to.

<p align="center">
  <img src="../assets/landing_page.png" alt="Griptape Nodes landing page">
</p>

These sample workflows are excellent resources for learning about Griptape Nodes' capabilities, but for now, let's start from scratch.

## Create a new workflow from scratch

On the landing page, locate and click on the **"Create from scratch"** tile.

<p align="center">
  <img src="../assets/create_from_scratch.png" alt="Create from scratch option">
</p>

This action opens a blank workspace where you can build custom workflows.

## Get familiar with the Griptape Nodes interface

Once you're in the Workflow Editor, take a moment to familiarize yourself with the interface:

<p align="center">
  <img src="../assets/workspace_interface.png" alt="Griptape Nodes workspace interface">
</p>

The most important area to focus on initially is the left panel, the node library, which contains the **"Create Nodes"** section. This panel houses all the standard nodes that come pre-packaged with Griptape Nodes.

<p align="center">
  <img src="../assets/create_nodes_panel.png" alt="Create Nodes panel">
</p>

Each node serves a specific function. As you become more familiar with Griptape Nodes, you'll learn how each one works and how they can be combined to create powerful automations.

## Adding Your First Node

Let's add a node to your workspace. You have two options:

1. **Drag and Drop**: Click and hold on a node from the left panel, then drag it onto your workspace.
1. **Double-Click**: Simply double-click any node in the left panel to automatically place it in the center of your workspace.

After adding a node, you can:

- Click and drag to reposition it on the workspace
- Connect it to other nodes (which we'll cover in just a few moments)

!!! info

    To follow the video exactly, create a "FloatInput" node and a "DisplayFloat" node

<p align="center">
  <img src="../assets/nodes_in_workspace.png" alt="Node on the workspace">
</p>

## Connecting Nodes

Now, very simply drag from a port on one node to a port on the other. We cheated a _little_ bit by picking nodes that are compatible (not all are), but there you have it. One connection between nodes - and you're building a graph.

<p align="center">
  <img src="../assets/connected.png" alt="Node on the workspace">
</p>

## Summary

In this tutorial, you learned how to:

- Launch Griptape Nodes
- Navigate through the landing page to a workflow
- Understand some of the most basic interface elements
- Add your first node(s) to the workspace
- Connect your nodes into a small workflow

Congratulations on taking your first steps with Griptape Nodes! With these fundamentals, you're well on your way to creating powerful, custom workflows.

## Next Up

In the next section: [Prompt an Image](../01_prompt_an_image/FTUE_01_prompt_an_image.md), we'll start in on the good stuff: making images!
