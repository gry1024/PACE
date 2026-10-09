# 模块说明
# 仅用于本地开发的私有邮件捕获 Adapter。
#
# 使用稳定 UUID 文件名保存邮件，返回 captured 而不是 provider_accepted。
# 不调用 SMTP / HTTP，也不打印收件地址或正文；捕获目录应放被忽略的私有位置。
# 临时文件写完并 fsync 后独占原子发布；本地捕获不代表真实发送。

"""Private local capture, explicitly not real email delivery."""

import json
import os
import tempfile
from pathlib import Path
from uuid import UUID


# 实现说明：CaptureEmail
# 通过落盘观察通知内容，同时保留与真实Email相同的Port签名。
#
# 仅适合合成 / 授权的本地测试，不代表邮件被对方收到。
class CaptureEmail:
    # 实现说明：CaptureEmail.__init__
    # 保存调用者指定的捕获目录，不创建全局默认收件箱。
    #
    # 目录应处于.local等不提交位置，调用者负责避免公开路径。
    def __init__(self, directory: Path):
        self.directory = directory

    # 实现说明：CaptureEmail.deliver
    # 以稳定 delivery_id 捕获一封邮件并检查重放内容一致性。
    #
    # 先规范化 UUID，防止任意路径注入；独占创建避免重试覆盖已有内容。
    # 新目录0700、新文件0600；已有目录权限不会自动收紧。
    # 同ID内容相同返回captured，内容不同报冲突，不覆盖既有内容。
    async def deliver(self, recipient: str, subject: str, body: str, delivery_id: str) -> str:
        # 只允许规范 UUID 文件名，不能使用包含斜杠或上级目录的任意字符串。
        safe_id = str(UUID(delivery_id))
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        path = self.directory / f"{safe_id}.json"
        payload = json.dumps(
            {"recipient": recipient, "subject": subject, "body": body}, ensure_ascii=False
        )
        # Exclusive create gives local retry deduplication. Conflicting input fails.
        # 独占创建保留首个交付内容；本地捕获的重复调用应幂等。
        # 先完成私有临时文件并 fsync，再原子独占链接，崩溃不留下半写的交付文件。
        descriptor, temporary = tempfile.mkstemp(prefix=".mail-", dir=self.directory)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            try:
                os.link(temporary, path)
                if hasattr(os, "O_DIRECTORY"):
                    directory_fd = os.open(self.directory, os.O_RDONLY | os.O_DIRECTORY)
                    try:
                        os.fsync(directory_fd)
                    finally:
                        os.close(directory_fd)
            except FileExistsError:
                if path.read_text(encoding="utf-8") != payload:
                    raise ValueError("Capture delivery ID has conflicting content.") from None
        finally:
            Path(temporary).unlink(missing_ok=True)
        # 这是开发捕获状态，绝不能改写为真实服务商接受或用户已读。
        return "captured"
