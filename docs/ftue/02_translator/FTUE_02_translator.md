# Coordinating Agents

Welcome to the third tutorial in our Griptape Nodes series! In this guide, you'll learn how to set up a translator workflow that demonstrates the powerful concept of coordinating multiple agents to perform sequential tasks.

## What You'll Learn

In this tutorial, you will:

- Create an agent that writes stories in Spanish
- Connect nodes to create a translation workflow
- Configure a second agent to translate to English
- Understand execution chains for controlling workflow order
- Test your workflow with different prompts

## Navigate to the Landing Page

To begin this tutorial, return to the main landing page by clicking on the navigation element at the top of the interface.

![Return to landing page](assets/return_to_landing.png)

## Open the Translator Example

On the landing page, locate and click on the **"Translator"** tile to open this example scene.

![Translator example](assets/translator_example.png)

## Setting Up the Initial Agent

The first step is to create an agent that will write a story in Spanish:

1. Locate the first agent node in the workflow
2. Notice that it's configured with a prompt to write a four-line story in Spanish
3. This agent will produce Spanish text as its output

![Spanish agent node](assets/spanish_agent_node.png)

## Integrating the Merge Texts Node

Next, we need to prepare the Spanish output for translation:

1. Find the "Merge Texts" node connected to the Spanish agent
2. This node combines the Spanish story with the instruction "rewrite this in English"
3. The combined text becomes the input for our next agent

![Merge texts node](assets/merge_texts_node.png)

## Configuring the Second Agent

Now, let's set up the translator agent:

1. Locate the second agent node in the workflow
2. This agent takes the merged text (Spanish story + translation instruction)
3. It processes the input and produces an English translation
4. The output connects to a display node to show the final result

![English agent node](assets/english_agent_node.png)

## Understanding the Execution Chain

A key concept in Griptape Nodes is the execution chain, which controls the order of operations:

1. Notice the lines connecting the nodes - these represent both data flow and execution order
2. The Spanish agent runs first, producing the original story
3. The Merge Texts node combines this output with translation instructions
4. The English agent runs next, producing the translated version
5. Finally, the display node shows the result

![Execution chain](assets/execution_chain.png)

## Testing with Different Prompts

Let's experiment with different inputs to see how our workflow adapts:

1. Modify the prompt for the first agent to "write me a haiku in Japanese"
2. Run the workflow again
3. Observe how the second agent still performs its translation task, now converting from Japanese to English

![Different prompt test](assets/different_prompt.png)

## Adding Additional Agents

To expand your workflow further:

1. Try adding a third agent with a different task, such as "tell me a bedtime story"
2. Connect it appropriately in the execution chain
3. Run the workflow and observe how the agents work together sequentially

![Additional agent](assets/additional_agent.png)

## Next Steps

Now that you understand how to coordinate multiple agents in a sequential workflow, you're ready to create more complex automations. In the next tutorial, we'll explore how to combine agents with image generation nodes.

## Summary

In this tutorial, you learned how to:
- Create an agent that writes stories in Spanish
- Connect nodes to create a translation workflow
- Configure a second agent to translate to English
- Understand execution chains for controlling workflow order
- Test your workflow with different prompts

These concepts form the foundation for more sophisticated Griptape Nodes workflows where multiple agents collaborate to accomplish complex tasks.

## Next Up

In the next section: [Advanced Prompt Techniques](../03_compare_prompts/FTUE_03_compare_prompts.md), we'll look at combining Agents and GenerateImage nodes in a first-step into more complicated flows.