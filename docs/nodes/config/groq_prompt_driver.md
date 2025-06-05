# Groq Prompt Driver

The Groq Prompt Driver node allows you to configure and utilize Groq's language models within the Griptape Nodes framework. This node provides access to Groq's high-performance inference engine and various language models.

## Configuration

### API Key

To use the Groq Prompt Driver, you need to provide a Groq API key. You can obtain an API key from the [Groq Console](https://console.groq.com/keys).

### Available Models

The Groq Prompt Driver supports the following models:

#### Production Models

- [gemma2-9b-it](https://huggingface.co/google/gemma-2-9b-it) - Google's Gemma 2 9B model
- [meta-llama/llama-guard-4-12b](https://console.groq.com/docs/model/llama-guard-4-12b) - Meta's Llama Guard model for content moderation
- [llama-3.3-70b-versatile](https://console.groq.com/docs/model/llama-3.3-70b-versatile) - Meta's versatile 70B parameter model
- [llama-3.1-8b-instant](https://console.groq.com/docs/model/llama-3.1-8b-instant) - Meta's fast 8B parameter model
- [llama3-70b-8192](https://console.groq.com/docs/model/llama3-70b-8192) - Meta's 70B parameter model with 8K context
- [llama3-8b-8192](https://console.groq.com/docs/model/llama3-8b-8192) - Meta's 8B parameter model with 8K context
- [meta-llama/llama-4-scout-17b-16e-instruct](https://console.groq.com/docs/model/llama-4-scout-17b-16e-instruct) - Meta's vision model with 16K context, compatible with the Image Description node
- [meta-llama/llama-4-maverick-17b-128e-instruct](https://console.groq.com/docs/model/llama-4-maverick-17b-128e-instruct) - Meta's vision model with 128K context, compatible with the Image Description node

#### Preview Models

- [allam-2-7b](https://ai.azure.com/explore/models/ALLaM-2-7b-instruct/version/2/registry/azureml) - Saudi Data and AI Authority's 7B parameter model
- [deepseek-r1-distill-llama-70b](https://console.groq.com/docs/model/deepseek-r1-distill-llama-70b) - DeepSeek's distilled 70B parameter model

### Parameters

The Groq Prompt Driver supports the following configuration parameters:

| Parameter    | Type    | Default      | Description                                          |
| ------------ | ------- | ------------ | ---------------------------------------------------- |
| model        | string  | gemma2-9b-it | The Groq model to use for text generation            |
| temperature  | float   | 0.7          | Controls randomness in the output (0.0 to 1.0)       |
| top_p        | float   | 0.9          | Controls diversity via nucleus sampling (0.0 to 1.0) |
| max_tokens   | integer | 2048         | Maximum number of tokens to generate                 |
| stream       | boolean | false        | Whether to stream the response                       |
| max_attempts | integer | 3            | Maximum number of retry attempts for failed requests |

## Usage

1. Add the Groq Prompt Driver node to your workflow
1. Make sure to get an API key here: [Groq API Keys](https://console.groq.com/keys)
1. Configure your `GROQ_API_KEY` in the Griptape Configuration settings
1. Select your desired model from the available options
1. Adjust the generation parameters as needed
1. Connect the node to other nodes in your workflow

## Notes

- The Groq Prompt Driver uses the OpenAI-compatible API endpoint at `https://api.groq.com/openai/v1`
- Preview models are intended for evaluation purposes and may be discontinued at short notice
- Production models are recommended for production environments
- The node automatically handles API key validation before workflow execution
