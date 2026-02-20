"""Shared helpers for importing user-specified Python modules by file path or dotted name."""

from __future__ import annotations

import importlib
import importlib.util
import sys
from pathlib import Path
from types import ModuleType


def import_module_spec(
    module_spec: str, config_path: Path | None = None, *, label: str = "module"
) -> ModuleType:
    """Import a module by file path or dotted module name.

    Args:
        module_spec: File path (``*.py`` or containing ``/``) or a dotted
            Python module name.
        config_path: Used to resolve relative file paths against the config
            file's parent directory.
        label: Human-readable label for error messages (e.g. ``"contracts"``).

    Returns:
        The imported module.

    Raises:
        ImportError: If the module cannot be loaded from a file path.
    """
    if is_file_path(module_spec):
        path = resolve_module_path(module_spec, config_path, label=label)
        module_name = f"olly_{label}_{path.stem}_{abs(hash(str(path)))}"
        spec = importlib.util.spec_from_file_location(module_name, path)
        if spec is None or spec.loader is None:
            raise ImportError(f"Could not load {label} module from {path}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
        return module
    return importlib.import_module(module_spec)


def is_file_path(module_spec: str) -> bool:
    """Return True if *module_spec* looks like a file path rather than a dotted module name."""
    return module_spec.endswith(".py") or "/" in module_spec or "\\" in module_spec


def resolve_module_path(
    module_spec: str, config_path: Path | None = None, *, label: str = "module"
) -> Path:
    """Resolve a file-path module spec to an absolute ``Path``.

    Args:
        module_spec: Relative or absolute path to a ``.py`` file.
        config_path: If provided, relative paths are resolved against its
            parent directory; otherwise ``cwd`` is used.
        label: Human-readable label for error messages.

    Returns:
        Resolved absolute path.

    Raises:
        FileNotFoundError: If the resolved path does not exist.
    """
    path = Path(module_spec)
    if not path.is_absolute():
        base_dir = Path.cwd()
        if config_path is not None:
            base_dir = config_path.parent
        path = base_dir / path
    path = path.resolve()
    if not path.exists():
        raise FileNotFoundError(f"{label.capitalize()} file not found: {path}")
    return path
