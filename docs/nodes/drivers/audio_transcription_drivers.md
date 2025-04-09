# OpenAiAudioTranscriptionDriver

## What is it?

The OpenAiAudioTranscriptionDriver is a building block that lets you set up a connection to OpenAI's audio transcription service (Whisper). Think of it as configuring a special tool that can listen to audio and convert it to text.

## When would I use it?

Use this node when you want to:

- Convert speech in audio files to text
- Transcribe recordings for your workflow
- Use speech as input for your AI agents

## How to use it

### Basic Setup

1. Add the OpenAiAudioTranscriptionDriver to your workspace
1. Connect it to your flow
1. Connect its output to nodes that need to transcribe audio

### Optional Configuration

- **model**: The Whisper model to use (default is "whisper-1")

### Outputs

- **driver**: The configured audio transcription driver that other nodes can use

## Example

Imagine you want to transcribe an audio recording and then analyze the text:

1. Add an OpenAiAudioTranscriptionDriver to your workflow
1. Leave the default "whisper-1" model or specify a different one
1. Connect the "driver" output to a node that processes audio files
1. When you run the flow, the audio will be converted to text that other nodes can process

## Important Notes

- You need a valid OpenAI API key set up in your environment as `OPENAI_API_KEY`
- The default model is "whisper-1" which works well for most transcription needs
- This node only configures the transcription service - you'll need other nodes to actually process audio files

## Common Issues

- **Missing API Key**: Make sure your OpenAI API key is properly set up
- **Connection Errors**: Check your internet connection and API key validity
- **Unsupported Audio Format**: Make sure your audio files are in a format supported by Whisper
