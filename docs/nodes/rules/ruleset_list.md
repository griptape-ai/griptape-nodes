# RulesetList

## What is it?

The RulesetList node combines multiple rulesets into a single list. This allows for more complex behaviors to be defined for an agent by grouping multiple rulesets together.

## When would I use it?

Use the RulesetList node when:

- You need to combine multiple rulesets to create more complex agent behaviors
- You want to organize different sets of rules into a single collection
- You're building an agent that needs to follow multiple sets of rules simultaneously
- You want to modularly combine different rule systems

## How to use it

### Basic Setup

1. Add a RulesetList node to your workflow
1. Connect up to four individual ruleset nodes to the input parameters (ruleset_1, ruleset_2, ruleset_3, ruleset_4)
1. Connect the output (rulesets) to any node that accepts a list of rulesets as input

### Parameters

- **ruleset_1**: The first ruleset to add to the combined list
- **ruleset_2**: The second ruleset to add to the combined list
- **ruleset_3**: The third ruleset to add to the combined list
- **ruleset_4**: The fourth ruleset to add to the combined list

### Outputs

- **rulesets**: A combined list containing all non-null input rulesets

## Example

A common use case is combining multiple specialized rulesets for an agent:

1. Add a Ruleset node to your workflow, name it "Conversation Rules"
1. Add a Ruleset node to your workflow, name it "Task Rules"
1. Add a RulesetList node to your workflow
1. Connect a "Conversation Rules" ruleset to your RulesetList node's ruleset_1
1. Connect a "Task Rules" ruleset to your RulesetList node's ruleset_2
1. Connect the output (rulesets) to an Agent node's ruleset input
