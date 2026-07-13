"""Optional reasoning graph visualizer plugin.

The main package intentionally does not import this module. Removing the plugin
directory leaves the case workflow unchanged.
"""

from .snapshot import SNAPSHOT_SCHEMA_VERSION, build_snapshot, load_snapshot, save_snapshot

__all__ = [
    "SNAPSHOT_SCHEMA_VERSION",
    "build_snapshot",
    "load_snapshot",
    "save_snapshot",
]
