# Ruleset

## What is it?

The Ruleset Node allows you to create and output a Ruleset object. Rulesets consist of a name and a list of rules, which can be used with other nodes like agents in your workflow.

## When would I use it?

Use this node when you want to:

- Constrain or direct the output of another node that generates responses from an LLM

## How to use it

### Basic Setup

1. Add the Ruleset to your workflow
1. Set the "name" parameter to define the name for your ruleset (optional, defaults to "Behavior")
1. Set the "rules" parameter to define the list of rules for your ruleset (optional, defaults to an empty string, comma separated)
1. Connect it to your flow (specifically into nodes that have a Ruleset parameter)

### Parameters

- **name**: A single parameter that is created and output by this node
- **rules**: A single parameter that is created and output by this node

### Outputs

- **ruleset**: The output Ruleset object as a property or input for another node

## Example

Imagine you want to create a new ruleset with the following name and rules:

1. Add a Ruleset to your workflow

1. Set the "name" parameter to:

    ```
    MyBehavioralRules
    ```

1. Set the "rules" parameter to:

    ```
    Rule 1: This is my first rule.
    Rule 2: This is my second rule.
    Rule 3: This is my third rule.
    ```

1. Connect the output of this node to an agent's Ruleset parameter

## Important Notes

- The Ruleset Node supports string values only
- If no initial value is provided, default values are used for name and rules
- This node can be used in conjunction with other nodes to create dynamic Ruleset objects based on other parameters or properties
