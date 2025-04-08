# AudioTranscriptionTool

## What is it?

The AudioTranscriptionTool is a custom node in Griptape that utilizes the OpenAI audio transcription service to transcribe audio files. It's designed to work seamlessly with other nodes in the Griptape workflow.

## When would I use it?
Use this node when you want to:
- Transcribe audio files using the OpenAI service
- Integrate the OpenAI audio transcription service with other nodes in your workflow
- Validate the necessary configuration for the OpenAI API

## How to use it

### Basic Setup

1. Add the AudioTranscriptionTool to your workspace
1. Connect it to other nodes that provide necessary input parameters (e.g., off_prompt, driver)

### Fields
- **off_prompt**: A boolean indicating whether to use an off-prompt for the transcription.
- **driver**: The audio transcription driver to use. If not provided, defaults to OpenAiAudioTranscriptionDriver.

### Outputs
- **tool**: The created AudioTranscriptionTool instance

## Example
Imagine you have a workflow that generates and saves text:

1. Create a flow with several nodes (like an agent that generates text and a node that saves it)
1. Add the AudioTranscriptionTool at the end of your sequence, connecting it to nodes that provide off_prompt and driver parameters
1. Run the flow to see the audio transcription in action

## Important Notes

- The AudioTranscriptionTool requires the OpenAI API key to be set as an environment variable.
- Using the AudioTranscriptionTool with an invalid or missing driver will raise a ValueError.

## Validation
The `validate_node` method checks for the following:
- If the driver is provided, it returns an empty list of exceptions.
- If the OpenAI API key is not defined as an environment variable, it raises a KeyError.
- If the OpenAI API client fails to authenticate, it raises an AuthenticationError.

## Common Issues
- **Invalid Driver**: Ensure that you're providing a valid driver when connecting this node to other nodes in your workflow.
- **Missing API Key**: Verify that the OpenAI API key is set as an environment variable for the AudioTranscriptionTool to function correctly.
