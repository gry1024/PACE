# 模块说明：Gmail 账号键的纯规范化，不负责证明邮箱所有权。
"""Gmail-only identity normalization; verification belongs to Google OIDC."""

import re


def canonical_gmail(email: str) -> str:
    """仅接收个人 gmail.com；点号和 plus alias 归到同一邮箱键。"""
    value = email.strip().lower()
    if value.count("@") != 1:
        raise ValueError("A personal Gmail address is required.")
    local, domain = value.split("@")
    if domain != "gmail.com" or not re.fullmatch(r"[a-z0-9.]+(?:\+[a-z0-9._-]+)?", local):
        raise ValueError("A personal Gmail address is required.")
    local = local.split("+", 1)[0].replace(".", "")
    if not local:
        raise ValueError("A personal Gmail address is required.")
    return f"{local}@gmail.com"
