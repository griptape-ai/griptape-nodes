- A loop set to "Run Group Items All at Once" no longer sends the editor every event about the
  temporary copies of its body. A 24-item loop used to send about 7,000 messages and 6 MB the
  editor could only discard, which is enough to make it report the engine as disconnected.
  [#5067](https://github.com/griptape-ai/griptape-nodes-engine/issues/5067)
