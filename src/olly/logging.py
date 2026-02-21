from __future__ import annotations

import logging


def setup_logging(verbose: bool = False) -> None:
    """Configure the ``olly`` logger hierarchy.

    Args:
        verbose: When True, set level to DEBUG; otherwise WARNING.
    """
    level = logging.DEBUG if verbose else logging.INFO
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(name)s: %(message)s"))
    root = logging.getLogger("olly")
    root.setLevel(level)
    root.addHandler(handler)
