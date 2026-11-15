import hashlib
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


@dataclass(frozen=True, slots=True)
class RateLimit:
    name: str
    limit: int
    window: timedelta

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("Rate limit name must not be empty")
        if self.limit < 1:
            raise ValueError("Rate limit must allow at least one hit")
        if self.window < timedelta(seconds=1):
            raise ValueError("Rate limit window must be at least one second")

    def window_start(self, now: datetime) -> datetime:
        elapsed = (now - _EPOCH) // self.window
        return _EPOCH + elapsed * self.window

    def retry_after(self, now: datetime) -> int:
        remaining = self.window_start(now) + self.window - now
        return max(1, int(remaining.total_seconds() + 0.999))

    def key_hash(self, subject: str) -> str:
        return hashlib.sha256(f"{self.name}\0{subject}".encode()).hexdigest()


class RateLimitExceededError(Exception):
    def __init__(self, retry_after: int) -> None:
        super().__init__("Rate limit exceeded")
        self.retry_after = retry_after
