- Node libraries can build a `NodeError` for a failed provider call with `NodeError.missing_secret`,
  `NodeError.from_http_response` and `NodeError.from_request_exception`, instead of each library
  writing its own helpers. A refused API key links to the secret in Settings, and timeouts and
  failed connections get a plain message.
  [#5899](https://github.com/griptape-ai/griptape-nodes-engine/issues/5899)
