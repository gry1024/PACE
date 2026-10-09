# 模块说明：检查当前文档链接、围栏和 CODEMAP 的实现文件覆盖。
# 不再维护旧模块卡片指纹；语义复核由 coding task 同步 authoritative docs。
"""Validate current docs without accessing external services or private files."""

import re
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parent.parent


def check() -> list[str]:
    """只读校验当前文档；历史来源保留原文，不检查 Notion 内部 URL。"""
    paths = [ROOT / "README.md", ROOT / "AGENTS.md"]
    paths.extend(p for p in (ROOT / "docs").rglob("*.md") if "sources" not in p.parts)
    errors = []
    for path in paths:
        body = path.read_text(encoding="utf-8")
        if len(re.findall(r"^\s*```", body, re.M)) % 2:
            errors.append(f"{path.relative_to(ROOT)}: unclosed fence")
        body = re.sub(r"^```[^\n]*\n.*?^```\s*$", "", body, flags=re.M | re.S)
        for raw in re.findall(r"\]\(([^)]+)\)", body):
            link = urlsplit(raw.strip().strip("<>"))
            if link.scheme or link.netloc:
                continue
            target = (path.parent / unquote(link.path)).resolve() if link.path else path
            if not target.is_relative_to(ROOT) or not target.is_file():
                errors.append(f"{path.relative_to(ROOT)}: missing target {raw}")
            elif link.fragment and target.suffix == ".md":
                headings = re.findall(r"^#+\s+(.+)$", target.read_text(encoding="utf-8"), re.M)
                anchors = {re.sub(r"[^\w\- ]", "", h.lower()).replace(" ", "-") for h in headings}
                if unquote(link.fragment) not in anchors:
                    errors.append(f"{path.relative_to(ROOT)}: missing anchor {raw}")
    codemap = (ROOT / "docs/CODEMAP.md").read_text(encoding="utf-8")
    # 有实质实现的 Python 文件必须有导航；不扫描秘密与第三方包。
    for directory in ("src", "tests", "scripts", "migrations"):
        for path in (ROOT / directory).rglob("*.py"):
            if path.name != "__init__.py" and "__pycache__" not in path.parts:
                relative = path.relative_to(ROOT).as_posix()
                if relative not in codemap:
                    errors.append(f"CODEMAP: unregistered implementation {relative}")
    print(f"Checked {len(paths)} documents; {len(errors)} errors.")
    return errors


if __name__ == "__main__":
    failures = check()
    for failure in failures:
        print(failure)
    raise SystemExit(bool(failures))
