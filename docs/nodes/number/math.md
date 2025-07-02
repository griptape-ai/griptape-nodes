# Math Operations

## What is it?

The Math node is a versatile mathematical operations node that can perform various arithmetic and mathematical functions on numbers. It supports both unary operations (single input) and binary operations (two inputs).

## When would I use it?

Use this node when you need to:

- Perform basic arithmetic operations (addition, subtraction, multiplication, division)
- Calculate mathematical functions (square root, absolute value, sine)
- Round numbers (round, ceil, floor)
- Find minimum/maximum values
- Calculate averages
- Perform modulo operations
- Calculate powers

## How to use it

### Basic Setup

1. Add the Math node to your workflow
1. Select the operation you want to perform from the dropdown menu
1. Connect input values to parameters A and B (B is only needed for binary operations)
1. The result will be available in the "result" output

### Available Operations

#### Binary Operations (require both A and B inputs)

- Add (A + B)
- Subtract (A - B)
- Multiply (A * B)
- Divide (A / B)
- Modulo (A % B)
- Power (A ^ B)
- Average (avg(A, B))
- Min (min(A, B))
- Max (max(A, B))

#### Unary Operations (only require A input)

- Square Root (√A)
- Round (round(A))
- Ceiling (⌈A⌉)
- Floor (⌊A⌋)
- Absolute Value (|A|)
- Sine (sin(A))

### Outputs

- **result**: The calculated result of the mathematical operation

## Example

Imagine you want to calculate the average of two numbers:

1. Add a Math node to your workflow
1. Select "average [avg(A, B)]" from the operation dropdown
1. Connect two number inputs to parameters A and B
1. The average will be available in the "result" output

## Implementation Details

The Math node automatically handles:

- Type conversion for inputs
- Division by zero (returns infinity)
- Modulo by zero (returns infinity)
- Dynamic parameter visibility (hides B parameter for unary operations)
