# ditto.recorders

Recorder protocol, registry, and built-in recorders.

`RECORDER_REGISTRY` discovers names from installed entry-point metadata and loads
each recorder on its first successful lookup. Membership checks, key iteration,
and `len()` do not load plugins. Names retain discovery order, followed by
additional assigned names in insertion order.

Assignment (including `register()`), `del`, and `clear()` do not load plugins.
Operations that read values, such as `get()`, iteration over `items()` or
`values()`, and `pop()`, can load plugins and raise `DittoRecorderLoadError`.

Pytest's `monkeypatch.setitem()` and `monkeypatch.delitem()` read the previous
value so they can restore it. For an existing entry point, this loads the plugin
and fails if it is broken. Direct assignment can override a broken entry point
without loading it. For isolated tests of `recorders.get()` and
`recorders.register()`, pass a plain dictionary through their `registry` argument.

::: ditto.recorders
    options:
      show_root_heading: false
      members_order: source
