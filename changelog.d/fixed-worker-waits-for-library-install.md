- A library whose nodes run in a worker process now starts its worker as soon as the library
  finishes installing. Its runs no longer fail with a "No module named" error after a first install
  until the engine restarts, and a library installed from Git while the editor is connected no
  longer goes without a worker until **Refresh Libraries**.
