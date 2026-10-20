- MCP clients can now call `GetNodeCatalogRequest` to list every node type's library, category,
  description, and deprecation in one request, instead of one `ListNodeTypesInLibraryRequest` per
  library. It reads library metadata only, so it loads no node code.
  [#5962](https://github.com/griptape-ai/griptape-nodes-engine/issues/5962)
