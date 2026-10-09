# 模块说明：收集器不得扫描额外文件或越过授权目录，使用原始换行哈希。
import importlib.util
from pathlib import Path

import pytest

from pace.application.contracts import SyncEntityInput

spec = importlib.util.spec_from_file_location(
    "collector",
    Path(__file__).parents[2] / "plugins/pace/scripts/collect.py",
)
collector = importlib.util.module_from_spec(spec)
spec.loader.exec_module(collector)


def test_collector_exact_selection_and_raw_hash(tmp_path):
    (tmp_path / "selected.md").write_bytes(b"original\r\ntext\r\n")
    (tmp_path / "unselected.txt").write_text("do not upload")
    result = SyncEntityInput.model_validate(collector.collect(tmp_path, ["selected.md"]))
    assert len(result.files) == 1 and result.files[0].text == "original\r\ntext\r\n"
    with pytest.raises(ValueError):
        collector.collect(tmp_path, ["selected.md", "selected.md"])
    with pytest.raises(ValueError):
        collector.collect(tmp_path, ["../secret.md"])


def test_external_symlink_rejected(tmp_path):
    root = tmp_path / "authorized"
    root.mkdir()
    outside = tmp_path / "private.md"
    outside.write_text("private")
    (root / "link.md").symlink_to(outside)
    with pytest.raises(ValueError):
        collector.collect(root, ["link.md"])
