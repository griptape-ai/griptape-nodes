- The engine installs and runs on Python 3.14 and 3.15. Node libraries still declare their own
  supported Python range, so a library capped at 3.12 does not load on a newer interpreter.
  [#5863](https://github.com/griptape-ai/griptape-nodes-engine/issues/5863)
