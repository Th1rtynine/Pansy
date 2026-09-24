"""桌面资料目录与旧预览版迁移：只碰临时目录，不读取真实用户资料。"""

from __future__ import annotations

import os
from pathlib import Path
import sys
import tempfile
from unittest import mock


PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from desktop import pansy_server  # noqa: E402


class Checks:
    def __init__(self) -> None:
        self.passed = 0
        self.failed = 0
        self.step = 0

    def check(self, label: str, passed: bool, detail: str = "") -> None:
        self.step += 1
        print(f"{'PASS' if passed else 'FAIL'} [{self.step:02d}] {label}" + (f"  -- {detail}" if detail else ""))
        if passed:
            self.passed += 1
        else:
            self.failed += 1


def main() -> int:
    checks = Checks()
    with tempfile.TemporaryDirectory(prefix="pansy-desktop-data-") as temporary:
        root = Path(temporary)

        with (
            mock.patch.object(sys, "platform", "win32"),
            mock.patch.dict(os.environ, {"LOCALAPPDATA": str(root)}, clear=False),
        ):
            checks.check(
                "桌面资料使用独立目录",
                pansy_server._app_data_dir() == root / "PansyData",
                str(pansy_server._app_data_dir()),
            )
            checks.check(
                "仍能找到旧预览版目录",
                pansy_server._legacy_app_data_dir() == root / "Pansy",
            )

        legacy = root / "legacy"
        target = root / "target"
        (legacy / "data" / "covers").mkdir(parents=True)
        (legacy / "config.toml").write_text("old-config", encoding="utf-8")
        (legacy / "data" / "pansy.db").write_bytes(b"old-database")
        (legacy / "data" / "covers" / "work-1.jpg").write_bytes(b"cover")

        with mock.patch.object(pansy_server, "_legacy_app_data_dir", return_value=legacy):
            copied = pansy_server._migrate_legacy_data(target)

        checks.check("首次启动复制配置与资料", copied == ["config.toml", "data"], repr(copied))
        checks.check(
            "数据库和封面一起迁移",
            (target / "data" / "pansy.db").read_bytes() == b"old-database"
            and (target / "data" / "covers" / "work-1.jpg").read_bytes() == b"cover",
        )

        (target / "config.toml").write_text("new-config", encoding="utf-8")
        (target / "data" / "pansy.db").write_bytes(b"new-database")
        with mock.patch.object(pansy_server, "_legacy_app_data_dir", return_value=legacy):
            copied_again = pansy_server._migrate_legacy_data(target)

        checks.check("再次启动不重复迁移", copied_again == [], repr(copied_again))
        checks.check(
            "绝不覆盖新位置已有资料",
            (target / "config.toml").read_text(encoding="utf-8") == "new-config"
            and (target / "data" / "pansy.db").read_bytes() == b"new-database",
        )
        checks.check(
            "迁移完成后没有临时残留",
            not any(".migrating-" in item.name for item in target.iterdir()),
        )

    print(f"\n{checks.passed} 项通过,{checks.failed} 项失败")
    return 1 if checks.failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
