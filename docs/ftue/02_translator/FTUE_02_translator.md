# Coordinating Agents

Welcome to the third tutorial in our Griptape Nodes series! In this guide, you'll learn how to coordinate multiple agents within a workflow to perform sequential tasks—specifically, translating stories between languages and summarizing them.

## What we'll cover

In this tutorial, we will:

- Study then recreate a translation workflow between agents working sequentially
- Discover how to "merge texts" to take outputs and modify them into new prompts
- Learn about the "exec chain" for controlling workflow execution order
- Build more into the template workflow to add a summarization task

## Navigate to the Landing Page

To begin this tutorial, go to the landing page via the nav bar with the Griptape Nodes logo in the top left. Locate and open the example workflow called "Translator" at the top of the page.

<p align="center">
  <img src="../assets/translator_example.png" alt="Translator example">
</p>

## Explore the Template Workflow

When the template loads, you'll see a workflow with the following components:

<p align="center">
  <img src="../assets/workflow_overview.png" alt="Workflow overview">
</p>

- **Agent Node (spanish_story)**: Generates a four-line story in Spanish
- **Merge Text Node**: Combines the Spanish story with "Rewrite this in English"
- **Second Agent Node (to_english)**: Translates the merged prompt into English
- **Display Text Node**: Shows the final English translation

This workflow demonstrates how multiple agents can each perform their own distinct "jobs."

By connecting one agent's output to another through a **MergeTexts** node, you create _new_ prompts that direct the next agent's behavior.

All a **MergeTexts** node does is stick the incoming texts together using the "merge string" to separate them.  The default merge string is just two "newlines": ```\n\n```. In the example here, I've simply typed "Rewrite this in English:" into **input_1** of the MergedTexts node, but _connected_ the output of my **spanish_story** node into **input_2**. When run, the MergeTexts node will resolve and output the two texts merged:

  > Rewrite this in English:
  >
  > Bajo la luna, el río cantó,  
  > Un secreto antiguo en su agua dejó.  
  > La niña lo escuchó y empezó a soñar,  
  > Que el mundo era suyo, listo para amar.


This approach enables controlled yet sophisticated interactions. In this example, we first prompt one agent to "write a 4-line story in Spanish" and then incoporate that spanish story result into a _new_ prompt for a _second_ agent to translate that Spanish text into English, producing the following result:

<p align="center">
  <img src="../assets/workflow_result.png" alt="Workflow result"  width="500">>
</p>

!!! info

    You should expect variability in these from run-to-run. That's okay! Remember, talking with an Agent can in a way be like talking to a person. You may get slightly different answers if you ask them the same question many times.

## Build a sibling workflow

Let's build another almost identical flow just below this one, to get some practice creating and connecting nodes.

1. Drag two **Agent** nodes onto the canvas
1. Add a **MergeTexts** node
1. Add a **DisplayText** node

## Configure the First Agent

Set up your first agent to generate content in your chosen language:

1. In the first agent node, enter: `Write me a four line story in [your chosen language]` (e.g., Mandarin, French, etc.)
1. This agent will generate the initial story that we'll translate

<p align="center">
  <img src="../assets/mandarin.png" alt="Story setup" width="400">
</p>

## Connect to the Merge Text Node

Next, prepare the translation prompt:

1. Connect the output from the first agent to the merge text node
1. Set the merge text node to combine: `Rewrite this in English` with the output from the first agent
1. This creates the instruction for our translator agent

<p align="center">
  <img src="../assets/mandarin_merge.png" alt="Merge text setup">
</p>

## Configure the Second Agent

Set up the translator agent:

1. Connect the output of the merge text node to the second agent node
1. This agent will receive both the original story and the instruction to translate it
1. It will produce an English translation as output

<p align="center">
  <img src="../assets/mandarin_to_english.png" alt="Second agent setup">
</p>

## Display the Result

To see the final translation:

1. Connect the output of the second agent to the display text node
1. When the workflow runs, this node will show the translated English text

<p align="center">
  <img src="../assets/mandarin_display.png" alt="Display setup"  width="500">>
</p>

## Understand Execution Order (Exec Chain)

A key concept in Griptape Nodes is the execution chain:

1. Notice the "exec in" and "exec out" pins (half-circle connectors) on nodes
1. These define the order in which nodes run
1. For complex workflows, connect the last pin of one section to the first pin of the next
1. This ensures nodes run in the correct sequence, even with complex data flows

<p align="center">
  <img src="../assets/exec_chain.png" alt="Execution chain">
</p>

## Expand the Workflow: Summarize Multiple Stories

Let's enhance our workflow to handle summarization:

1. Add a new merge text node that combines both English translations
1. In this merge text node, enter: `Summarize both these stories` as the first entry
1. Connect both the to-english nodes' outputs into slots 2&3 on the merge texts node
1. Add another agent node to process the summary prompt
1. Connect the merge text output into the prompt for your new agent
1. Connect the agent output to a new display text node
1. Use exec chain pins to ensure this summary step runs last (even connect everything up to run in the order you want!)

<p align="center">
  <img src="../assets/summary_pre.png" alt="Expanded workflow">
</p>

## Run the Complete Workflow

Execute your expanded workflow and observe the process:

1. The first agents generate stories in different languages
1. The merge text nodes create prompts to translate them
1. The second agents translate the stories into English
1. The summary agent combines and summarizes both translations
1. The display nodes show all the results

<p align="center">
  <img src="../assets/final_result.png" alt="Final result" width="500">
</p>

!!! info

    Again, remember! Look for this _construction_ in the response you get, not that it matches what you see here - it is likely to be wildly different!

## Summary

In this tutorial, we covered:

- How a workflow can hand things off between agents to perform tasks like translation
- Discover how "merge texts" allows you to take outputs and modify them into new prompts
- Learned about the "exec chain" for controlling workflow execution order
- Built more into the template workflow to add a summarization task

## Next Up

In the next section: [Compare Prompts](../03_compare_prompts/FTUE_03_compare_prompts.md), we'll learn how to get AIs to bucket-brigade through flows!
