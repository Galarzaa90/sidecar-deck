from __future__ import annotations

import asyncio
from collections import deque
from datetime import datetime, timezone
from typing import Deque

from .config import Settings
from .models import MetricPayload, StatusEnvelope


class MetricsState:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.latest: MetricPayload | None = None
        self.history: Deque[MetricPayload] = deque()
        self.latest_received_at: datetime | None = None
        self.real_metrics_received = False
        self._condition = asyncio.Condition()

    async def set_metrics(self, payload: MetricPayload, *, source: str) -> None:
        stamped = payload.with_timestamp()
        async with self._condition:
            self.latest = stamped
            self.latest_received_at = datetime.now(timezone.utc)
            if source == "real":
                self.real_metrics_received = True
            self.history.append(stamped)
            self._trim_history()
            self._condition.notify_all()

    async def wait_for_update(self, last_seen: datetime | None, timeout: float = 30) -> StatusEnvelope:
        async with self._condition:
            if self.latest_received_at == last_seen:
                try:
                    await asyncio.wait_for(self._condition.wait(), timeout=timeout)
                except TimeoutError:
                    pass
            return self.snapshot()

    def snapshot(self) -> StatusEnvelope:
        now = datetime.now(timezone.utc)
        age = None
        if self.latest_received_at is not None:
            age = max(0.0, (now - self.latest_received_at).total_seconds())

        status = "waiting"
        if age is not None:
            if age >= self.settings.metrics_offline_seconds:
                status = "offline"
            elif age >= self.settings.metrics_stale_seconds:
                status = "stale"
            else:
                status = "live"

        return StatusEnvelope(
            status=status,
            serverTime=now,
            ageSeconds=age,
            staleAfterSeconds=self.settings.metrics_stale_seconds,
            offlineAfterSeconds=self.settings.metrics_offline_seconds,
            latest=self.latest,
            history=list(self.history),
        )

    def _trim_history(self) -> None:
        cutoff = datetime.now(timezone.utc).timestamp() - self.settings.history_seconds
        while self.history and self._timestamp(self.history[0]) < cutoff:
            self.history.popleft()

    @staticmethod
    def _timestamp(payload: MetricPayload) -> float:
        if payload.timestamp is None:
            return 0
        timestamp = payload.timestamp
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)
        return timestamp.timestamp()
