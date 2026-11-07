"""Transport policy. An untested tunnel is never advertised as a working endpoint."""

from dataclasses import dataclass

from moss_studio.domain.contracts import ValidationError

CHECKS = {"upload", "generate", "progress", "cancel", "reconnect", "download", "auth"}


@dataclass(frozen=True)
class TransportEvidence:
    mode: str
    checks: dict[str, bool]
    requires_sse: bool

    def require_pass(self) -> None:
        if self.mode not in {"quick_polling", "named", "colab_protected"}:
            raise ValidationError("E_TRANSPORT：未知或未支援的連線模式")
        if self.mode == "quick_polling" and self.requires_sse:
            raise ValidationError("E_TRANSPORT：Quick Tunnel 不能放行需要 SSE 的路徑")
        if set(self.checks) != CHECKS or any(value is not True for value in self.checks.values()):
            raise ValidationError("E_TRANSPORT：入口完整操作及認證尚未實測通過")
