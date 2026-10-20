"""Web 登录失败限制，适用于当前单进程部署，重启后记录清空。"""
from dataclasses import dataclass
from math import ceil
from time import monotonic


@dataclass
class LoginAttempt:
    failures: int
    expires_at: float
    banned: bool = False


class LoginLimiter:
    def __init__(self):
        self.max_failures = 5
        self.window_seconds = 15 * 60
        self.ban_seconds = 15 * 60
        self._attempts: dict[str, LoginAttempt] = {}
        self._next_cleanup = 0.0

    def _get_attempt(self, ip: str, now: float):
        if now >= self._next_cleanup:
            self._attempts = {
                key: attempt for key, attempt in self._attempts.items()
                if attempt.expires_at > now
            }
            self._next_cleanup = now + 60

        attempt = self._attempts.get(ip)
        if attempt and attempt.expires_at <= now:
            del self._attempts[ip]
            return None
        return attempt

    def retry_after(self, ip: str) -> int:
        now = monotonic()
        attempt = self._get_attempt(ip, now)
        if attempt and attempt.banned:
            return ceil(attempt.expires_at - now)
        return 0

    def record_failure(self, ip: str) -> None:
        now = monotonic()
        attempt = self._get_attempt(ip, now)
        if attempt is None:
            attempt = LoginAttempt(0, now + self.window_seconds)
            self._attempts[ip] = attempt
        if attempt.banned:
            return
        attempt.failures += 1
        if attempt.failures >= self.max_failures:
            attempt.banned = True
            attempt.expires_at = now + self.ban_seconds

    def reset(self, ip: str) -> None:
        self._attempts.pop(ip, None)


login_limiter = LoginLimiter()
