**Tutorial Title: Creating a Translator Workflow with Multiple Agents**

**Introduction:**
In this tutorial, you will learn how to set up a translator workflow using multiple agents, each assigned different tasks. This example will demonstrate the basic concept of using agents to perform sequential tasks, laying the groundwork for more complex workflows.

**Prerequisites:**
- Basic understanding of workflow automation
- Familiarity with agents and nodes in a workflow system

**Steps:**

1. **Set Up the Initial Agent:**
   - Create an agent with a prompt to write a four-line story in Spanish.
   - Ensure the agent outputs the story in Spanish.

2. **Integrate the Merge Texts Node:**
   - Take the Spanish story output and input it into a merge texts node.
   - Add the line "rewrite this in English" to the input.

3. **Configure the Second Agent:**
   - Set up a second agent to take the merged text and rewrite the story in English.
   - Ensure the output is displayed in a display node.

4. **Test with Different Prompts:**
   - Try a different prompt, such as "write me a haiku in Japanese," to see how the workflow adapts.

5. **Understand the Execution Chain:**
   - Observe the execution order of agents. The first agent runs, followed by the second, based on input-output dependencies.
   - Learn to use the execution chain to control the order of operations definitively.

6. **Add Additional Agents:**
   - Experiment by adding another agent with a different task, such as "tell me a bedtime story."
   - Use the execution chain to ensure the desired order of execution.

**Expected Outcome:**
By the end of this tutorial, you will have a functional translator workflow that uses multiple agents to perform sequential tasks, translating a story from Spanish to English and adapting to different prompts.

**Troubleshooting:**
- If the agents do not execute in the correct order, check the execution chain settings.
- Ensure all inputs and outputs are correctly linked between nodes.

**Additional Resources:**
- Explore advanced workflow automation techniques to enhance your projects.
- Consider integrating more complex logic and additional agents for sophisticated tasks.


## Next Up

In the next section: [Advanced Prompt Techniques](../03_compare_prompts/FTUE_03_compare_prompts.md), we'll look at combining Agents and GenerateImage nodes in a first-step into more complicated flows.