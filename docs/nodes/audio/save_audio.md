# SaveAudio

## What is it?

The LoadAudio node is a simple building block that lets you save an audio file from your workflow so you can use it elsewhere.

## When would I use it?

Use this node when you want to:

- Save an audio file that was created by another node

## How to use it

### Basic Setup

1. Add the SaveAudio node to your workflow
1. Connect it to a parameter that outputs audio

### Parameters

- **audio**: The audio to save (this should be connected to an output from another node)

### Outputs

- **audio**: The name of the saved audio file that can be used elsewhere

## Example

Imagine you've generated some audio and want to save it on your computer, so that you can use it elsewhere:

1. Create a SaveAudio node
1. Connect the output of a parameter that generates audio
1. Enter the name of the file that you want to save the audio in
1. Resolve the node, either by clicking the run icon on the node itself, or using the run workflow or run selected options at the top of the editor.

## Important Notes

- The LoadAudio simply saves the audio to a file - it doesn't change the audio itself
- The audio will be saved in your current working directory
- The audio can be played by clicking the play button
