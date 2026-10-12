"""Routine checks.

Deterministic rules turn the day's text log into a short list of checked facts
(missed meal windows, long inactivity, possible falls). The LLM then writes the
family-facing summary from the log plus these facts. Keeping the checks in code
makes the flags reliable even with a 1.5B-parameter summary model.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta

EATING = re.compile(r"\b(eat|eats|eating|ate|meal|lunch|breakfast|dinner|snack|food|cook|cooking|stove|kitchen|drink|drinking)\b|吃|用餐|餐|煮|廚房|喝", re.I)
ALERT = re.compile(r"\b(lying on the floor|lying on the ground|fallen|has fallen|collapsed)\b|倒在地上|跌倒|躺在地上", re.I)


ZH_MEALS = {"breakfast": "早餐", "lunch": "午餐", "dinner": "晚餐"}


def hm(s: str) -> datetime:
    return datetime.strptime(s, "%H:%M")


def fmt(dt: datetime) -> str:
    return dt.strftime("%H:%M")


def is_alert(text: str) -> bool:
    return bool(ALERT.search(text))


def check_day(entries: list[dict], idle_spans: list[tuple[str, str]], routine: dict, lang: str = "en",
              day_end: str = "22:00") -> list[str]:
    """day_end: the time the report is written; windows that have not started yet are skipped."""
    zh = lang == "zh-TW"
    facts: list[str] = []
    seen = [e for e in entries if e.get("kind") == "observation" and not e.get("empty_scene")]
    report = hm(day_end)

    # 1. Meal windows set by the family.
    for meal in routine.get("meals", []):
        start, end = hm(meal["from"]), hm(meal["to"])
        if start >= report:
            continue
        in_window = [e for e in seen if start <= hm(e["clock"]) <= end]
        ate = [e for e in in_window if EATING.search(e["text"])]
        if ate:
            continue
        label = ZH_MEALS.get(meal["name"], meal["name"]) if zh else meal["name"]
        if not in_window:
            facts.append(f"{label}時段（{meal['from']}–{meal['to']}）沒有看到任何活動，也沒有看到用餐。" if zh else
                         f"No activity was seen during the usual {label} time ({meal['from']}–{meal['to']}), so no {label} was seen.")
        else:
            facts.append(f"{label}時段（{meal['from']}–{meal['to']}）有活動，但沒有看到用餐。" if zh else
                         f"There was activity during the usual {label} time ({meal['from']}–{meal['to']}), but no eating was seen.")

    # 2. Long inactivity during waking hours.
    limit = timedelta(minutes=int(routine.get("inactivity_alert_minutes", 180)))
    wake, sleep = hm(routine.get("awake_from", "07:00")), min(hm(routine.get("awake_to", "22:00")), report)
    for a, b in idle_spans:
        ta, tb = max(hm(a), wake), min(hm(b), sleep)
        if tb - ta >= limit:
            mins = int((tb - ta).total_seconds() // 60)
            alert_at = fmt(ta + limit)
            facts.append(f"{fmt(ta)} 到 {fmt(tb)} 之間約 {mins // 60} 小時 {mins % 60} 分鐘沒有任何活動，{alert_at} 已發出不活動提醒。" if zh else
                         f"No activity at all between {fmt(ta)} and {fmt(tb)} (about {mins // 60} h {mins % 60} min); "
                         f"an inactivity alert was sent at {alert_at}.")

    # 3. Possible falls.
    for e in seen:
        if is_alert(e["text"]):
            facts.append(f"{e['clock']} 的紀錄可能是跌倒：「{e['text']}」，已立即通知。" if zh else
                         f"At {e['clock']} the log suggests a possible fall (\"{e['text']}\"); an immediate alert was sent.")
    return facts
