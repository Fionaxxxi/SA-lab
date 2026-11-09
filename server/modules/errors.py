"""模块错误类型与契约错误码映射。

错误码以 contracts/ 与总计划 4.3 为准；模块内部只抛这些类型，
由网关层（林俊希）负责转成 HTTP 响应。
"""

from __future__ import annotations


class ModuleError(Exception):
    code = "MODULE_ERROR"
    http_status = 500

    def __init__(self, message: str, detail: dict | None = None):
        super().__init__(message)
        self.message = message
        self.detail = detail or {}

    def to_dict(self) -> dict:
        return {"code": self.code, "message": self.message, "detail": self.detail}


class InvalidPayload(ModuleError):
    code = "INVALID_PAYLOAD"
    http_status = 400


class NoSpeech(ModuleError):
    code = "NO_SPEECH"
    http_status = 422


class NoTranscript(ModuleError):
    code = "NO_TRANSCRIPT"
    http_status = 422


class ModelUnavailable(ModuleError):
    code = "MODEL_UNAVAILABLE"
    http_status = 503


class DeadlineExceeded(ModuleError):
    code = "DEADLINE_EXCEEDED"
    http_status = 504
