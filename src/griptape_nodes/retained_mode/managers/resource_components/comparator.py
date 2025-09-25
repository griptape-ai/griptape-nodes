from enum import StrEnum


class Comparator(StrEnum):
    """String-based comparators for resource requirement matching."""

    EQUALS = "=="
    NOT_EQUALS = "!="
    GREATER_THAN = ">"
    GREATER_THAN_OR_EQUAL = ">="
    LESS_THAN = "<"
    LESS_THAN_OR_EQUAL = "<="
    STARTS_WITH = "startswith"
    INCLUDES = "includes"  # substring match
    NOT_PRESENT = "~"  # key should not exist
    HAS_ANY = "has_any"  # container has any of the required items
    HAS_ALL = "has_all"  # container has all of the required items
    CUSTOM = "custom"  # allows ResourceType to implement custom comparison logic
