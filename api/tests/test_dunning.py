"""Régua de cobrança — 100% determinística (FLUXOS.md §5)."""

from datetime import date, datetime
from zoneinfo import ZoneInfo

from app.dunning.rules import (
    AllowedHours,
    decide,
    parse_steps,
    promise_pauses,
    within_allowed_hours,
)


STEPS = parse_steps(None)


def test_opt_out_skips():
    result = decide(
        today=date(2026, 10, 20),
        due_date=date(2026, 10, 17),
        steps=STEPS,
        opt_out=True,
        active_promise=None,
        sent=set(),
    )
    assert result.action == "skip"
    assert result.reason == "opt_out"


def test_active_promise_pauses_until_next_day():
    assert promise_pauses(date(2026, 10, 18), date(2026, 10, 17))
    assert not promise_pauses(date(2026, 10, 19), date(2026, 10, 17))

    result = decide(
        today=date(2026, 10, 18),
        due_date=date(2026, 10, 10),
        steps=STEPS,
        opt_out=False,
        active_promise=date(2026, 10, 17),
        sent=set(),
    )
    assert result.action == "skip"
    assert result.reason == "promessa_ativa"


def test_sends_current_step_once():
    result = decide(
        today=date(2026, 10, 17),
        due_date=date(2026, 10, 17),
        steps=STEPS,
        opt_out=False,
        active_promise=None,
        sent=set(),
    )
    assert result.action == "send"
    assert result.step and result.step.key == "D0"
    assert result.channels == ("whatsapp",)

    again = decide(
        today=date(2026, 10, 17),
        due_date=date(2026, 10, 17),
        steps=STEPS,
        opt_out=False,
        active_promise=None,
        sent={("D0", "whatsapp")},
    )
    assert again.action == "skip"
    assert again.reason == "etapa_ja_enviada"


def test_late_cycle_sends_only_latest_step():
    result = decide(
        today=date(2026, 10, 22),
        due_date=date(2026, 10, 17),
        steps=STEPS,
        opt_out=False,
        active_promise=None,
        sent=set(),
    )
    assert result.action == "send"
    assert result.step and result.step.key == "D+5"


def test_d30_hands_off_to_human():
    result = decide(
        today=date(2026, 11, 20),
        due_date=date(2026, 10, 17),
        steps=STEPS,
        opt_out=False,
        active_promise=None,
        sent=set(),
    )
    assert result.action == "handoff"
    assert result.step and result.step.key == "D+30"


def test_allowed_hours_respects_timezone_and_weekday():
    hours = AllowedHours.from_json({"start": "08:00", "end": "20:00", "weekdays": [0, 1, 2, 3, 4]})
    tz = "America/Sao_Paulo"
    monday_morning = datetime(2026, 10, 19, 11, 0, tzinfo=ZoneInfo(tz))
    monday_night = datetime(2026, 10, 19, 21, 0, tzinfo=ZoneInfo(tz))
    sunday = datetime(2026, 10, 18, 11, 0, tzinfo=ZoneInfo(tz))
    assert within_allowed_hours(monday_morning, hours, tz)
    assert not within_allowed_hours(monday_night, hours, tz)
    assert not within_allowed_hours(sunday, hours, tz)
