# Date and Time

## What is it?

The Date and Time tool is a utility that helps you format and manipulate date and time information as text.

## When would I use it?

Use this node when you want to:

- Format dates and times in specific text formats
- Convert between different date/time formats
- Generate date/time strings for use in text
- Create time-based text content

## How to use it

### Basic Setup

1. Add the Date and Time tool to your workflow
1. Configure the date/time parameters
1. Connect its output to nodes that need formatted date/time text

### Parameters

- **prompt**: The thing you'd like to get the date for (e.g. "Christmas, 2027", "Next friday")
- **format**: The format for the date/time (e.g., "%Y-%m-%d %H:%M:%S", "Fri 25, March, 9pm")

### Outputs

- **output**: The formatted date/time as text

## Example

Imagine you want to format a date in a specific way:

1. Add a Date and Time tool to your workflow
1. Set the desired date format
1. Connect the "output" to another node that needs the formatted date/time

## Implementation Details

The Date and Time tool provides flexible date and time formatting capabilities. It supports various format strings and timezone handling to generate properly formatted date/time text.
