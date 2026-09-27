"""Add the plugin's requirement on pytest-ditto to its dependencies.

Plugins are released in lockstep with pytest-ditto, from the same git tag, so each
requires at least the core it was released with: plugin X.Y.Z requires
``pytest-ditto>=X.Y.Z,<3``. The local segment (``+sha`` on untagged commits) is
dropped because PEP 440 doesn't allow it in a ``>=`` specifier. ``<3`` is the plugin
contract's major version.

The plugin's other dependencies are listed under
``[tool.hatch.metadata.hooks.custom]`` in its ``pyproject.toml``. A wheel built from
the sdist takes all of them from ``PKG-INFO`` and doesn't run this hook.

Every plugin carries an identical copy of this file, so it ships in each sdist.
"""

from typing import Any

from hatchling.metadata.plugin.interface import MetadataHookInterface
from packaging.version import Version

CORE_MAJOR = 2


class CoreFloorHook(MetadataHookInterface):
    def update(self, metadata: dict[str, Any]) -> None:
        floor = Version(metadata["version"]).public
        metadata["dependencies"] = [
            f"pytest-ditto>={floor},<{CORE_MAJOR + 1}",
            *self.config.get("dependencies", []),
        ]
