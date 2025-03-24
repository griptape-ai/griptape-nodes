from typing import Any, Generic, TypeVar

T = TypeVar("T")


class State:
    @staticmethod
    def on_enter(context: Any) -> type["State"] | None:  # noqa: ARG004
        """Called when entering the state."""
        return None

    @staticmethod
    def on_update(context: Any) -> type["State"] | None:  # noqa: ARG004
        """Called each update until a transition occurs."""
        return None

    @staticmethod
    def on_exit(context: Any) -> None:  # noqa: ARG004
        """Called when exiting the state."""
        return


class FSM(Generic[T]):
    def __init__(self, context: T) -> None:
        self._context = context
        self._current_state = None

    def start(self, initial_state: type[State]) -> None:
        # Enter the initial state.
        self.transition_state(initial_state)

    def get_current_state(self) -> type[State] | None:
        return self._current_state

    def transition_state(self, new_state: type[State] | None) -> None:
        while new_state is not None:
            # Exit the current state.
            if self._current_state is not None and new_state is self._current_state:
                new_state = self._current_state.on_update(self._context)
                continue
            if self._current_state is not None:
                self._current_state.on_exit(self._context)
            # Update current
            self._current_state = new_state
            # Enter the now-current state
            new_state = self._current_state.on_enter(self._context)

    def update(self) -> None:
        if self._current_state is None:
            new_state = None
        else:
            new_state = self._current_state.on_update(self._context)

        if new_state is not None:
            self.transition_state(new_state)
