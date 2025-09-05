from typing import Any, TypeVar

T = TypeVar("T")


class State:
    @staticmethod
    async def on_enter(context: Any) -> type["State"] | None:  # noqa: ARG004
        """Called when entering the state."""
        return None

    @staticmethod
    async def on_update(context: Any) -> type["State"] | None:  # noqa: ARG004
        """Called each update until a transition occurs."""
        return None

    @staticmethod
    async def on_exit(context: Any) -> None:  # noqa: ARG004
        """Called when exiting the state."""
        return

    @staticmethod
    async def on_event(context: Any, event: Any) -> type["State"] | None:  # noqa: ARG004
        """Called on an event, which may trigger a State transition."""
        return None


class FSM[T]:
    def __init__(self, context: T) -> None:
        self._context = context
        self._current_state = None

    async def start(self, initial_state: type[State]) -> None:
        # Enter the initial state.
        await self.transition_state(initial_state)

    @property
    def current_state(self) -> type[State] | None:
        return self._current_state

    @current_state.setter
    def current_state(self, value: type[State] | None) -> None:
        self._current_state = value

    @property
    def context(self) -> T:
        return self._context

    async def transition_state(self, new_state: type[State] | None) -> None:
        while new_state is not None:
            # Exit the current state.
            if self._current_state is not None and new_state is self._current_state:
                new_state = await self._current_state.on_update(self._context)
                continue
            if self._current_state is not None:
                await self._current_state.on_exit(self._context)
            # Update current
            self._current_state = new_state
            # Enter the now-current state
            new_state = await self._current_state.on_enter(self._context)

    async def update(self) -> None:
        if self._current_state is None:
            new_state = None
        else:
            new_state = await self._current_state.on_update(self._context)

        if new_state is not None:
            await self.transition_state(new_state)

    async def handle_event(self, event: Any) -> None:
        if self._current_state is None:
            new_state = None
        else:
            new_state = await self._current_state.on_event(self._context, event)

        if new_state is not None:
            await self.transition_state(new_state)
