"""The HomeLog pipeline: frame -> trigger -> VLM sentence -> encrypted log -> frame deleted -> daily summary."""

from __future__ import annotations

import gc
import json
import re
import time
from datetime import datetime, timedelta
from pathlib import Path

from . import prompts
from .backends import Backend
from .frames import MotionTrigger, sample_frames, to_jpeg
from .logbook import EncryptedLog
from .routine import check_day, is_alert

EMPTY_MARKERS = ("no one is in view", "畫面中沒有人")


def _clock(start: str, plus_sec: float) -> str:
    return (datetime.strptime(start, "%H:%M") + timedelta(seconds=plus_sec)).strftime("%H:%M")


def _clip_duration(path: str) -> float:
    import cv2
    cap = cv2.VideoCapture(path)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    n = cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0
    cap.release()
    return n / fps if n else 0.0


def run_scenario(scenario: dict, cfg: dict, vlm: Backend, llm: Backend, log: EncryptedLog,
                 base_dir: Path, echo=print) -> dict:
    lang = cfg.get("language", "en")
    every = float(cfg.get("sample_every_sec", 4))
    trigger = MotionTrigger(threshold=float(cfg.get("motion_threshold", 0.01)),
                            heartbeat_sec=float(cfg.get("heartbeat_sec", 0)))
    log.clear()

    segments_out, idle_spans, latencies = [], [], []

    for si, seg in enumerate(scenario["segments"]):
        if seg["type"] == "idle":
            idle_spans.append((seg["from"], seg["to"]))
            entry = {"kind": "idle", "clock": seg["from"], "until": seg["to"],
                     "text": seg.get("note", "No motion detected. VLM idle."), "segment": si}
            log.append(entry)
            segments_out.append({"type": "idle", "from": seg["from"], "to": seg["to"]})
            echo(f"{seg['from']}–{seg['to']}  · no motion, VLM idle")
            continue

        video = str((base_dir / seg["file"]).resolve())
        trigger.reset()
        last_text = None
        duration = _clip_duration(video)
        # A short clip can stand for a longer stretch of the day: span_minutes maps
        # clip seconds onto clock minutes (default: real time).
        span_sec = float(seg.get("span_minutes", 0)) * 60 or duration
        scale = span_sec / duration if duration else 1.0
        for t, frame in sample_frames(video, every):
            fire, changed = trigger.check(frame, t)
            if not fire:
                del frame
                continue
            jpeg = to_jpeg(frame)
            del frame  # the raw frame is gone
            t0 = time.perf_counter()
            text = vlm.chat(prompts.VLM_USER[lang], image_jpeg=jpeg, system=prompts.VLM_SYSTEM[lang])
            ms = (time.perf_counter() - t0) * 1000
            del jpeg  # the encoded frame is gone; only `text` remains
            gc.collect()
            text = " ".join(text.split()).strip("'\"")
            if not text:
                echo(f"{_clock(seg['clock'], t * scale)}  (no answer from the VLM, skipped · {ms:.0f} ms)")
                continue
            if text == last_text:
                # Same scene as last time: the frame is still deleted, but no duplicate line is logged.
                echo(f"{_clock(seg['clock'], t * scale)}  (unchanged, not logged · frame deleted)")
                continue
            last_text = text
            latencies.append(ms)
            entry = {
                "kind": "observation",
                "clock": _clock(seg["clock"], t * scale),
                "text": text,
                "empty_scene": text.lower().strip(" .。") in EMPTY_MARKERS,
                "alert": is_alert(text),
                "frame_deleted": True,
                "segment": si,
                "video_t": round(t, 2),
                "latency_ms": round(ms),
            }
            log.append(entry)
            echo(f"{entry['clock']}  {text}   [frame deleted · {ms:.0f} ms]" + ("   !! ALERT" if entry["alert"] else ""))
        segments_out.append({"type": "video", "clock": seg["clock"], "file": seg["file"],
                             "label": seg.get("label", ""), "duration": round(duration, 2),
                             "until": _clock(seg["clock"], span_sec)})

    entries = log.read()
    day_end = scenario.get("report_at", "22:00")
    facts = check_day(entries, idle_spans, scenario["routine"], lang, day_end=day_end)
    lines = []
    for e in entries:
        if e["kind"] == "idle":
            lines.append(f"{e['clock']}–{e['until']} no activity detected")
        else:
            lines.append(f"{e['clock']} {e['text']}")
    t0 = time.perf_counter()
    name = scenario["routine"].get("name", "Mom")
    user = prompts.summary_user(lang, name, lines, facts, day_end)
    summary, attempts = "", 0
    for attempts in range(1, 4):
        summary = " ".join(llm.chat(user, system=prompts.SUMMARY_SYSTEM[lang]).split())
        missing = _missing_facts(summary, facts, lang) + _unknown_times(summary, lines, facts, day_end, lang)
        if not missing:
            break
        echo(f"  (summary check: draft {attempts} missed {len(missing)} fact(s), asking again)")
        user = prompts.summary_user(lang, name, lines, facts, day_end) + prompts.retry_note(lang, missing)
    else:
        summary = _patch_summary(summary, _missing_facts(summary, facts, lang), facts, name, lang,
                                 _unknown_times(summary, lines, facts, day_end, lang, raw=True))
        echo("  (summary check: model kept missing facts, added them from the rules)")
    summary_ms = (time.perf_counter() - t0) * 1000

    return {
        "meta": {
            "scenario": scenario.get("title", ""),
            "report_at": day_end,
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "backend": vlm.name,
            "stub": vlm.name == "stub",
            "vlm_model": getattr(vlm, "model", "stub"),
            "llm_model": getattr(llm, "model", "stub"),
            "language": lang,
            "sample_every_sec": every,
            "avg_describe_ms": round(sum(latencies) / len(latencies)) if latencies else None,
            "summary_ms": round(summary_ms),
            "summary_attempts": attempts,
            "footage_credit": scenario.get("footage_credit", ""),
        },
        "segments": segments_out,
        "entries": entries,
        "summary": {"text": summary, "flags": facts},
    }


def write_demo_data(result: dict, out_path: Path) -> None:
    """Plain-text export for the demo page only. The device itself keeps the log encrypted."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    # Also as a JS file so the demo page opens straight from disk (no server needed).
    js = out_path.with_suffix(".js")
    js.write_text("window.HOMELOG_DAY = " + json.dumps(result, ensure_ascii=False) + ";\n", encoding="utf-8")


_MEALS = {"breakfast": "早餐", "lunch": "午餐", "dinner": "晚餐"}


def _fact_keys(fact: str, lang: str) -> list[str]:
    """Words a summary must contain to count as covering this fact."""
    low = fact.lower()
    for en, zh in _MEALS.items():
        if en in low or zh in fact:
            return [en, zh]
    if "inactivity" in low or "不活動" in fact:
        t = re.search(r"\d\d:\d\d", fact)
        return [t.group(0)] if t else []
    if "fall" in low or "跌倒" in fact:
        return ["fall", "floor", "跌倒", "地上"]
    return []


def _missing_facts(summary: str, facts: list[str], lang: str) -> list[str]:
    low = summary.lower()
    missing = [f for f in facts if (k := _fact_keys(f, lang)) and not any(x.lower() in low for x in k)]
    if facts and ("normal" in low or "一切正常" in summary):
        missing.append("Do not say the day looks normal; there are checked facts." if lang != "zh-TW"
                       else "有需要留意的事，不能說一切正常。")
    return missing


def _unknown_times(summary: str, lines: list[str], facts: list[str], day_end: str, lang: str, raw: bool = False) -> list[str]:
    """Times in the summary that appear nowhere in the log or facts: the model made them up."""
    known = set(re.findall(r"\d\d:\d\d", " ".join(lines + facts) + " " + day_end))
    bad = [t for t in dict.fromkeys(re.findall(r"\d\d:\d\d", summary)) if t not in known]
    if raw:
        return bad
    return [(f"{t} 不在紀錄裡，不要使用這個時間。" if lang == "zh-TW" else f"{t} is not in the log; do not use that time.") for t in bad]


def _patch_summary(summary: str, missing: list[str], facts: list[str], name: str, lang: str,
                   bad_times: list[str] | None = None) -> str:
    sents = re.split(r"(?<=[.!?。！？])\s*", summary)
    keep = [x for x in sents if x and "normal" not in x.lower() and "一切正常" not in x
            and not any(t in x for t in (bad_times or []))]
    add = [f for f in facts if f in missing]
    tail = (f"現在打個電話給{name}問候一下吧。" if lang == "zh-TW" else f"You may want to give {name} a call now.")
    return " ".join(keep + add + ([tail] if facts and not re.search(r"call|電話", " ".join(keep), re.I) else []))
