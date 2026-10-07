# ditto.exceptions

pytest-ditto's own exceptions subclass `DittoException`. Some misuse raises a
standard `TypeError` or `ValueError` instead, and errors from recorders and
backends propagate unchanged. Advisory warnings use the `DittoWarning` category.

::: ditto.exceptions
    options:
      show_root_heading: false
      members_order: source
