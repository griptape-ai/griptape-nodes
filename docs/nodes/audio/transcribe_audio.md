# TranscribeAudio

## What is it?

The TranscribeAudio node uses OpenAI's models to convert audio into text. It supports multiple transcription models and can work with both direct model configuration and agent-based transcription.

## When would I use it?

Use this node when you want to:

- Convert speech to text
- Transcribe audio recordings
- Extract text from audio files
- Process voice input into written form
- Create transcripts of audio content

## How to use it

### Basic Setup

1. Add the TranscribeAudio node to your workflow
1. Connect an audio source to the "audio" input
1. Choose a transcription model or connect an agent
1. Run the node to generate the transcription

### Parameters

- **agent**: An optional existing agent configuration to use for transcription
- **model**: The transcription model to use (defaults to "gpt-4o-mini-transcribe")
- **audio**: The audio file to transcribe (required)
- **output**: The transcribed text output

### Outputs

- **output**: The transcribed text from the audio
- **agent**: The agent object used for transcription, which can be connected to other nodes

## Example

A complete workflow for recording and transcribing audio:

1. Add a Microphone node to capture audio
1. Connect the Microphone's "audio" output to the TranscribeAudio node's "audio" input
1. Select your preferred transcription model
1. Run the workflow
1. The transcribed text will be available in the "output" parameter

## Important Notes

- The node requires a valid OpenAI API key set up in your environment as `OPENAI_API_KEY`
- Available models include:
    - gpt-4o-mini-transcribe
    - gpt-4o-transcribe
    - whisper-1
- You can provide your own agent configuration for more customized behavior
- The quality of transcription depends on the audio quality and the selected model

## Common Issues

- **Missing API Key**: Ensure your OpenAI API key is properly set up as the environment variable
- **No Audio Provided**: Make sure you've connected a valid audio source to the "audio" input
- **Poor Transcription Quality**: Try using a different model or improving the audio quality
- **Processing Errors**: Very long audio files or poor audio quality might result in less accurate transcriptions
