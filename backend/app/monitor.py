from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Monitor:
    started_at: datetime = field(default_factory=datetime.utcnow)
    counters: Counter = field(default_factory=Counter)

    def inc(self, key: str) -> None:
        self.counters[key] += 1

    def as_dict(self) -> dict:
        uptime = (datetime.utcnow() - self.started_at).total_seconds()
        data = dict(self.counters)
        data["uptime_seconds"] = uptime
        return data
