# ditto.recorders

The `Recorder` type, the recorder registry, and helpers for writing a recorder.

`RECORDER_REGISTRY` discovers names from installed entry-point metadata and loads
each recorder on its first successful lookup. A recorder's name is also its
persisted identifier. Membership checks, key iteration, `len()` and `problems`
do not load plugins. Names retain discovery order, followed by names added with
`register()` in the order they were added.

Every registration is checked against the plugin contract when the registry is
built, so `problems` is complete without loading anything, and loading a
recorder never changes it. A pytest run with any problem stops before
collection.

The registry is read-only apart from `register()`, which adds a recorder under
a new name and raises `DittoRecorderConflictError` if the name conflicts with
one already registered. Registered recorders cannot be replaced or removed.
Operations that read values, such as `get()` and iteration over `items()` or
`values()`, can load plugins and raise `DittoRecorderLoadError`. The `fallback`
argument to `recorders.get()` applies only to absent names; it does not
suppress errors from an installed recorder that fails to load.

`copy.copy(RECORDER_REGISTRY)` creates an independent registry without loading
plugins. Already loaded recorder objects are shared, while later registrations
affect only the registry they are made in. For isolated tests of
`recorders.get()` and `recorders.register()`, pass a `RecorderRegistry([], [])`
through their `registry` argument.

::: ditto.recorders
    options:
      show_root_heading: false
      members_order: source
