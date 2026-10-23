- A `NodeError` response over 16 KB now keeps its structure, with base64 data replaced by its length
  and strings over 2000 characters cut, instead of being dropped. It is dropped only if it is still
  too large.
  [#5899](https://github.com/griptape-ai/griptape-nodes-engine/issues/5899)
