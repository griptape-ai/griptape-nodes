# LoadAudio

## What is it?

The LoadAudio node is a simple building block that lets you bring an audio file into your workflow. Think of it as picking up an audio recording so you can use it in your project.

## When would I use it?

Use this node when you want to:

- Use an audio file that was created by another node
- Pass an audio file to other nodes in your workflow
- Process an audio file as part of your project

## How to use it

### Basic Setup

1. Add the LoadAudio node to your workflow
1. Connect it to a source of audio (like the Transcribe Audio node)

### Parameters

- **audio**: The audio to load (this can be connected to an output from another node)

### Outputs

- **audio**: The loaded audio that can be used by other nodes in your flow

## Example

Imagine you've recorded some audio and have it saved on your computer, and you'd like to use it elsewhere:

1. Create a LoadAudio node
1. Click on the load audio button, and choose your audio file from disk
1. The LoadAudio will make the audio available to use in the rest of your workflow

## Important Notes

- The LoadAudio simply passes the audio through - it doesn't change the audio itself
- You can click the file browser icon to select an audio file from your computer
- The audio can be played by clicking the play button
