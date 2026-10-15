- The agent chat on Windows no longer fails on every message with "`LocalWorkspaceBackend` only
  supports POSIX platforms" when the workspace has an `.agents/skills` folder. If a platform
  cannot load skills, the chat now answers without them instead of failing.
