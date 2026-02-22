"""State storage package for olly snapshot history.

Re-exports the public API so callers can write::

    from olly.state import StateDB, open_state, get_olly_dir
"""

from olly.state.base import BaseStateStore, open_state
from olly.state.sqlite import StateDB, get_olly_dir
from olly.state.warehouse import WarehouseStateStore

__all__ = [
    "BaseStateStore",
    "StateDB",
    "WarehouseStateStore",
    "get_olly_dir",
    "open_state",
]
