- `SetNodeMetadataRequest` now accepts `keys_to_remove`, a list of metadata keys to delete from a
  node. Clients can use it to clear a metadata key that was added earlier, which setting
  `metadata` alone cannot do.
