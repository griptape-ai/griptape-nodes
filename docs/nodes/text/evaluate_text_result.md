# Evaluate Text Result

The Evaluate Text Result node allows you to evaluate text outputs against specific criteria using Griptape's Eval Engine. This node is useful for validating AI-generated content, checking factual accuracy, or assessing the quality of text outputs.

## Inputs

- **Examples** (Property): Choose from preset examples or create your own evaluation

    - Options:

        - Choose a preset..
        - Paraphrase
        - Factual
        - Analogy

- **Input** (Input/Property): The input text to be evaluated

    - Supports multiline text input

- **Expected Output** (Input/Property): The expected or reference output text

    - Single line text input

- **Actual Output** (Input/Property): The actual output text to be evaluated

    - Single line text input

- **Criteria** (Input/Property): The evaluation criteria to use

    - Supports multiline text input
    - Example: "Does the output accurately paraphrase the input without losing meaning?"

## Outputs

- **Score** (Output): A float value between 0 and 1 representing the evaluation score

    - 1.0 indicates perfect match
    - 0.0 indicates complete mismatch

- **Reason** (Output): A detailed explanation of the evaluation result

    - Provides feedback on why the score was given
    - Explains any discrepancies found

## Example Usage

### Paraphrase Evaluation

```python
Input: "The quick brown fox jumps over the lazy dog."
Expected Output: "A swift brown fox leaps above a sleeping dog."
Actual Output: "A fast fox jumps over a dog that's not awake."
Criteria: "Does the output accurately paraphrase the input without losing meaning?"
```

### Factual Evaluation

```python
Input: "The capital of France is Paris."
Expected Output: "Paris is the capital city of France."
Actual Output: "France's capital is Paris."
Criteria: "Is the output factually correct based on the input?"
```

### Analogy Evaluation

```python
Input: "A bird is to sky as a fish is to ______."
Expected Output: "water"
Actual Output: "concrete"
Criteria: "Does the output correctly complete the analogy?"
```

## Notes

- The node uses Griptape's Eval Engine to perform the evaluation
- The evaluation is based on the provided criteria
- The score is normalized between 0 and 1
- The reason provides detailed feedback about the evaluation
- You can use preset examples or create your own custom evaluations
