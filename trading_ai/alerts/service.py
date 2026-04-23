from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field


class AlertRecord(BaseModel):
    level: str
    message: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    details: dict[str, Any] = Field(default_factory=dict)


@dataclass(slots=True)
class AlertService:
    max_records: int = 200
    _records: list[AlertRecord] = field(default_factory=list)

    def emit(self, level: str, message: str, **details: Any) -> AlertRecord:
        record = AlertRecord(level=level, message=message, details=details)
        self._records.append(record)
        self._records = self._records[-self.max_records :]
        return record

    def list_recent(self, limit: int = 50) -> list[AlertRecord]:
        return list(reversed(self._records[-limit:]))
