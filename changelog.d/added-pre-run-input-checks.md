- Node libraries can refuse an image or video input a provider will reject before the node runs,
  with `image_errors`, `video_errors` and `check_count` from `griptape_nodes.exe_types.input_checks`.
  They read the file's format, size, pixel size, length and frame rate locally and return an error
  that names the parameter, the value and the limit, and links the provider's page; anything they
  can't read locally, such as a remote URL, is left for the provider. See
  [Checking inputs before a run](https://docs.griptapenodes.com/en/stable/development/custom_nodes/error_handling/#checking-inputs-before-a-run).
  [#5960](https://github.com/griptape-ai/griptape-nodes-engine/issues/5960)
