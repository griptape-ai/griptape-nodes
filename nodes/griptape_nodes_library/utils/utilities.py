import re


def to_pascal_case(string) -> str:
    """Convert a string to PascalCase."""
    # First, replace any non-word character with a space
    string = re.sub(r"[^\w\s]", " ", string)

    # Replace underscores with spaces
    string = string.replace("_", " ")

    # Split the string into words
    words = string.split()

    # Capitalize the first letter of each word after the first word
    return "".join(word.capitalize() for word in words)
