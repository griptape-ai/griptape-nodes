- Engine processes now read `GTN_APPEND_PYTHONPATH`, a list of folders added to the end of the
  module search path. Modules in those folders can be imported from nodes, but never replace the
  engine's own packages the way `PYTHONPATH` entries can.
