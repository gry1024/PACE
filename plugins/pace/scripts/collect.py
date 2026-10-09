# 模块说明：Host 本地显式文件列表 → 私有同步 JSON，不联网、不递归扫描。
"""Collect only explicitly selected UTF-8 TXT/Markdown beneath an authorized root."""

import argparse
import hashlib
import json
import os
import stat
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4


def collect(root, paths, request_id=None):
    """越界 / 重复 / 超预算整体失败；原样保留换行和 UTF-8 内容。"""
    root = Path(root).resolve(strict=True)
    files, seen = [], set()
    if not root.is_dir() or not 1 <= len(paths) <= 20:
        raise ValueError("Select 1–20 files beneath an authorized directory.")
    for relative in paths:
        path = Path(relative)
        if path.is_absolute() or ".." in path.parts:
            raise ValueError("Only contained relative paths are allowed.")
        resolved = (root / path).resolve(strict=True)
        if (
            not resolved.is_relative_to(root)
            or resolved.suffix.lower() not in {".txt", ".md"}
            or path.suffix.lower() not in {".txt", ".md"}
        ):
            raise ValueError("Only contained TXT/Markdown files are allowed.")
        if resolved in seen:
            raise ValueError("Duplicate source file.")
        seen.add(resolved)
        # 非阻塞打开后立即检查常规文件，避免命名管道伪装成 .md 导致收集挂起。
        flags = os.O_RDONLY | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_NOFOLLOW", 0)
        descriptor_fd = os.open(resolved, flags | getattr(os, "O_BINARY", 0))
        with os.fdopen(descriptor_fd, "rb") as stream:
            if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                raise ValueError("Source must be a regular file.")
            # Linux 验证已打开 FD 的最终对象，防止路径校验后被换成外部 symlink。
            descriptor = Path(f"/proc/self/fd/{stream.fileno()}")
            if descriptor.is_symlink() and not descriptor.resolve().is_relative_to(root):
                raise ValueError("Opened source escaped the authorized directory.")
            raw = stream.read(1024 * 1024 + 1)
        if len(raw) > 1024 * 1024:
            raise ValueError("Source exceeds 1 MiB.")
        text = raw.decode("utf-8")
        source_id = "local:" + hashlib.sha256(str(resolved).encode()).hexdigest()
        files.append(
            {
                "source_id": source_id,
                "name": path.name,
                "text": text,
                "content_hash": hashlib.sha256(raw).hexdigest(),
                "observed_at": datetime.now(UTC).isoformat(),
            }
        )
    if sum(len(f["text"].encode()) for f in files) > 8 * 1024 * 1024:
        raise ValueError("Sources exceed 8 MiB total.")
    return {"request_id": str(UUID(request_id) if request_id else uuid4()), "files": files}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True)
    parser.add_argument("--file", action="append", required=True, dest="files")
    parser.add_argument("--output", required=True)
    parser.add_argument("--request-id")
    args = parser.parse_args()
    value = collect(args.root, args.files, args.request_id)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    # 拒绝覆盖，避免重试悄悄改变已授权 / 已提交的载荷。
    descriptor = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False)
    print(json.dumps({"status": "collected", "files": len(value["files"])}))


if __name__ == "__main__":
    main()
