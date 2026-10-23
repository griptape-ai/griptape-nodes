- Loading libraries, at engine startup and on a library reload or project switch, no longer runs
  git several times per library or re-reads every package installed in the engine's environment.
  With three libraries installed, a reload takes about 0.2 seconds instead of 1.9.
  [#5940](https://github.com/griptape-ai/griptape-nodes-engine/issues/5940)
