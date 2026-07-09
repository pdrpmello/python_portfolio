"""Dataclasses de domínio do monitor.

Camada 100% pura: sem dependências de projeto ou de terceiros (ADR-0004).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, time
from enum import Enum


@dataclass(frozen=True)
class TimePeriod:
    """Intervalo de horário dentro de um único dia (não cruza meia-noite)."""

    start: time
    end: time
    label: str = ""

    def __post_init__(self) -> None:
        if self.start >= self.end:
            raise ValueError(
                f"Período inválido: início {self.start} deve ser antes do fim {self.end}"
            )

    def duration_minutes(self) -> int:
        return (self.end.hour * 60 + self.end.minute) - (
            self.start.hour * 60 + self.start.minute
        )


@dataclass(frozen=True)
class ResourceSchedule:
    """Agenda ocupada de um recurso (aeronave ou Stand By) em um dia."""

    name: str
    model: str = ""
    busy_periods: tuple[TimePeriod, ...] = ()


@dataclass(frozen=True)
class DaySchedule:
    """Escala de um dia como lida da página do SAGA."""

    day: date
    sunrise: time
    sunset: time
    resources: tuple[ResourceSchedule, ...] = ()


class PeriodStatus(Enum):
    AVAILABLE = "available"
    BUSY = "busy"


@dataclass(frozen=True)
class ClassifiedPeriod:
    """Período do relatório: 🟢 (AVAILABLE) ou 🔴 (BUSY) com motivo legível."""

    period: TimePeriod
    status: PeriodStatus
    reason: str


@dataclass(frozen=True)
class ResourceAvailability:
    resource_name: str
    resource_model: str
    periods: tuple[ClassifiedPeriod, ...] = ()


@dataclass(frozen=True)
class DayAvailability:
    """Resultado das regras de disponibilidade para um dia.

    window=None significa dia sem janela operacional (ex.: nascer do sol
    após o horário-limite do dia da semana).
    """

    day: date
    sunrise: time
    sunset: time
    window: TimePeriod | None
    resources: tuple[ResourceAvailability, ...] = ()


@dataclass(frozen=True)
class ScanError:
    """Erro recuperável na leitura de um dia (PRD F10)."""

    day_index: int
    day_label: str
    message: str


@dataclass(frozen=True)
class ScanResult:
    days: tuple[DaySchedule, ...] = ()
    errors: tuple[ScanError, ...] = ()
