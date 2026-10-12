#!/usr/bin/env python3
"""Run HomeLog over a scenario (a "day" built from video clips) and export the demo data.

    python run_day.py                       # real models via Ollama (see config.yaml)
    python run_day.py --backend stub        # plumbing test, no models needed
    python run_day.py --lang zh-TW          # Traditional Chinese log and summary
"""

from __future__ import annotations

import argparse
from pathlib import Path

import requests
import yaml

from homelog.backends import make_backend
from homelog.logbook import EncryptedLog, load_or_create_key
from homelog.pipeline import run_scenario, write_demo_data

ROOT = Path(__file__).resolve().parent


def main() -> None:
    ap = argparse.ArgumentParser(description="HomeLog day runner")
    ap.add_argument("--config", default=str(ROOT / "config.yaml"))
    ap.add_argument("--scenario", default=str(ROOT / "scenarios" / "demo_day.yaml"))
    ap.add_argument("--backend", choices=["ollama", "stub"], help="override config backend")
    ap.add_argument("--lang", choices=["en", "zh-TW"], help="override config language")
    ap.add_argument("--out", default=str(ROOT / "demo" / "data" / "day.json"))
    args = ap.parse_args()

    cfg = yaml.safe_load(Path(args.config).read_text(encoding="utf-8"))
    if args.backend:
        cfg["backend"] = args.backend
    if args.lang:
        cfg["language"] = args.lang
    scenario = yaml.safe_load(Path(args.scenario).read_text(encoding="utf-8"))

    vlm = make_backend(cfg, "vlm")
    llm = make_backend(cfg, "llm")
    log = EncryptedLog(str(ROOT / cfg.get("log_path", "data/homelog.log")),
                       load_or_create_key(cfg.get("key_path", "~/.homelog/key")))

    print(f"HomeLog · {scenario.get('title', '')} · backend={vlm.name} · lang={cfg.get('language', 'en')}\n")
    try:
        result = run_scenario(scenario, cfg, vlm, llm, log, base_dir=Path(args.scenario).resolve().parent.parent)
    except requests.ConnectionError:
        raise SystemExit(f"\nCannot reach the model server at {cfg['vlm']['base_url']}.\n"
                         "Start Ollama (open the Ollama app or run `ollama serve`), or test with --backend stub.")
    except requests.HTTPError as e:
        raise SystemExit(f"\nModel server error: {e}\nIs the model pulled? Try `ollama pull {cfg['vlm']['model']}` "
                         f"and `ollama pull {cfg['llm']['model']}`.")

    print("\nChecked facts:")
    for f in result["summary"]["flags"] or ["(none)"]:
        print(f"  - {f}")
    print("\nDaily summary:\n" + result["summary"]["text"])
    m = result["meta"]
    print(f"\nAverage frame description: {m['avg_describe_ms']} ms · summary: {m['summary_ms']} ms")

    out = Path(args.out)
    write_demo_data(result, out)
    print(f"\nEncrypted log: {log.path}\nDemo data: {out} (+ .js)")
    if result["meta"]["stub"]:
        print("NOTE: stub backend. This output is placeholder text, not model output.")


if __name__ == "__main__":
    main()
