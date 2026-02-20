"""Tests for load_syncs()."""

import pytest

from olly.checks.integrity import load_syncs
from olly.models import IntegrityMethod


def test_load_from_file(tmp_path):
    """Loading a Python file with a syncs list returns the syncs."""
    module_file = tmp_path / "my_syncs.py"
    module_file.write_text(
        "from olly.models import IntegrityMethod, Sync, WindowOp, WindowSpec\n"
        "syncs = [\n"
        "    Sync(\n"
        '        name="test_sync",\n'
        '        source="src",\n'
        '        target="tgt",\n'
        '        source_table="main.t1",\n'
        '        target_table="main.t2",\n'
        "        method=IntegrityMethod.COUNT,\n"
        '        watermark="ts",\n'
        "        window=WindowSpec(op=WindowOp.GT_NOW, duration='2h'),\n"
        "    ),\n"
        "]\n"
    )
    config_toml = tmp_path / "olly.toml"
    config_toml.write_text("")

    result = load_syncs("my_syncs.py", config_toml)
    assert len(result) == 1
    assert result[0].name == "test_sync"
    assert result[0].method == IntegrityMethod.COUNT


def test_load_missing_syncs_attribute(tmp_path):
    """Module without a syncs attribute raises ValueError."""
    module_file = tmp_path / "empty_mod.py"
    module_file.write_text("x = 1\n")
    config_toml = tmp_path / "olly.toml"
    config_toml.write_text("")

    with pytest.raises(ValueError, match="No 'syncs' attribute"):
        load_syncs("empty_mod.py", config_toml)


def test_load_empty_syncs(tmp_path):
    """Module with an empty syncs list raises ValueError."""
    module_file = tmp_path / "empty_list.py"
    module_file.write_text("syncs = []\n")
    config_toml = tmp_path / "olly.toml"
    config_toml.write_text("")

    with pytest.raises(ValueError, match="empty"):
        load_syncs("empty_list.py", config_toml)


def test_load_blank_module_spec():
    """Blank module_spec raises ValueError."""
    with pytest.raises(ValueError, match="integrity.module must be set"):
        load_syncs("  ")
