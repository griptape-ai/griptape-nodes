def next_multiple_ge(value: int, multiple_of: int) -> int:
    """Returns the next largest multiple greater than or equal to value."""
    if value % multiple_of == 0:
        return value
    return ((value // multiple_of) + 1) * multiple_of
