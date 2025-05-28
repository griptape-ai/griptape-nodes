# Random Text

The Random Text node allows you to select random content from input text or generate random content when no input is provided. It supports selecting random characters, words, sentences, or paragraphs.

## Parameters

### Input Text

- **Type**: String
- **Mode**: Input/Property
- **Description**: The text to select random content from. If empty, the node will generate random content based on the selection type.
- **UI Options**: Multiline enabled

### Seed

- **Type**: Integer
- **Mode**: Property
- **Description**: A seed value (0-10,000) for reproducible random selection. Using the same seed will produce the same random selection.
- **UI Options**: Slider with range 0-10,000

### Selection Type

- **Type**: String

- **Mode**: Property

- **Description**: The type of content to select or generate:

    - `character`: Selects a random character
    - `word`: Selects a random word
    - `sentence`: Selects a random sentence or generates a new one
    - `paragraph`: Selects a random paragraph or generates a new one

### Output

- **Type**: String
- **Mode**: Output
- **Description**: The randomly selected or generated content
- **UI Options**: Multiline enabled

## Behavior

- When input text is provided:

    - The node selects random content from the input based on the selection type
    - For sentences and paragraphs, it splits the input on appropriate delimiters
    - If no matching content is found, it falls back to generating new content

- When no input text is provided:

    - For characters: Generates a random character from letters, digits, and punctuation
    - For words: Generates a random English word
    - For sentences: Uses an AI agent to generate a natural-sounding sentence
    - For paragraphs: Uses an AI agent to generate a coherent paragraph

## Examples

### Selecting Random Content

```python
# Input text: "Hello world! This is a test. How are you today?"
# Selection type: word
# Output: "world" (randomly selected word)
```

### Generating Random Content

```python
# Input text: "" (empty)
# Selection type: sentence
# Output: "The quick brown fox jumps over the lazy dog." (AI-generated sentence)
```

## Notes

- The seed parameter ensures reproducible results when using the same value
- The node will show a loading message while generating content with the AI agent
