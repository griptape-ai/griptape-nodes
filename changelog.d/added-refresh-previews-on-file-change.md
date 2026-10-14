- The engine now watches each local file the editor previews and sends a `StaticFileChanged` event
  when the file is saved, including saves from other apps, so the editor can show the new content.
  Turn it off with the `refresh_previews_on_file_change` setting, and cap how many files are watched
  with `refresh_previews_max_files` (1000 by default).
  [griptape-vsl-gui#3273](https://github.com/griptape-ai/griptape-vsl-gui/issues/3273)
