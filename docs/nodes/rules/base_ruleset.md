# RulesetNode

## What is it?

The RulesetNode is a data node that allows you to create and manage rulesets. A ruleset is a collection of rules that can be applied to various inputs.

## When would I use it?

Use this node when you want to:

- Create and manage rulesets for your workflow
- Apply rules to specific inputs or outputs
- Validate and refine your rules

## How to use it

### Basic Setup

1. Add the RulesetNode to your workspace
1. Connect it to your flow
1. Connect a source of text to its input (e.g., "rules")

### Required Fields

- **name**: The name for your ruleset (usually connected from another node)
- **rules**: A string containing one or more rules, separated by newline characters

### Optional Configuration

- **output_path**: The filename and location where you want to save the ruleset (default is "griptape_output.txt")

### Outputs

- **ruleset**: The created ruleset object (this can be used by other nodes if needed)

## Example

Imagine you have a set of rules that you want to apply to your workflow:

1. Connect the "output" from another node to the "name" input of the RulesetNode
1. Set "rules" to a string containing one or more rules, separated by newline characters:

```
rule1: condition => action
rule2: condition => action
```

3. Run your flow
1. The created ruleset will be stored in the `ruleset` output

## Important Notes

- If you don't specify an output path, the ruleset will be saved to "griptape_output.txt" by default
- The node will create a new file or overwrite an existing file with the same name
- Make sure you have write permissions for the location where you're trying to save

## Common Issues

- **Empty File**: Check if you've connected text to the "rules" input
- **Invalid Rules**: Ensure that each rule is in the correct format (e.g., `condition => action`)
- **File Save Error**: Check if the path is valid and you have the necessary permissions
