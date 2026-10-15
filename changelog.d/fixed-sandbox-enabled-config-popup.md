- The editor no longer shows a "GetConfigValue Failed" popup for `library.sandbox_enabled` at
  launch or on refresh. `GetConfigValueRequest` now succeeds with an empty value for a setting
  that is unset by default, and fails only for a key that names no setting.
