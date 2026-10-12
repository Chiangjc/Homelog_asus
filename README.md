# HomeLog

**Home care that understands daily life, without keeping a single frame.**

HomeLog turns a home camera into a text diary. A vision-language model (VLM) writes one sentence about each frame, the frame is deleted, and only the sentence is kept in an encrypted log. Each evening a small language model (LLM) reads the day and sends the family a short update that points out anything unusual, such as a missed lunch or a long stretch without activity.

Team Bee · ASUS UGen AI League 2026 · Battlefield Lightning (ASUS UGen300)

## How it works

```
camera / video ─► motion trigger ─► VLM: one sentence ─► encrypted text log ─► frame deleted
                                                              │
                         routine checks (meals, inactivity) ◄─┘
                                        │
                            LLM: evening summary ─► family phone (text only)
```

| Stage | Prototype (laptop, Stage I) | Target (ASUS UGen300, Stage II) |
| --- | --- | --- |
| Trigger | Frame differencing + heartbeat | Lightweight person detector |
| Scene description | `qwen3-vl:2b` on Ollama | Qwen3-VL-2B / Qwen2-VL-2B on Hailo-10H |
| Daily summary | `qwen3:1.7b` on Ollama | Qwen3-1.7B / Qwen2.5-1.5B via Hailo-Ollama |
| Log | Fernet-encrypted JSON lines | same |

The model clients use the Ollama chat API. Hailo provides **Hailo-Ollama**, an Ollama-compatible server on HailoRT, so moving the summary model to the UGen300 is a change of `base_url` in `config.yaml`. The Hailo-10H model list is in the [Hailo Model Zoo GenAI](https://github.com/hailo-ai/hailo_model_zoo_genai/blob/main/docs/MODELS.rst).

### Privacy by design

- Frames are sampled into memory, JPEG-encoded in memory, sent to the local model and deleted. No image is ever written to disk (`homelog/frames.py`, `homelog/pipeline.py`).
- The VLM prompt allows only location and activity: no identity, appearance, clothing, emotion or health guesses (`homelog/prompts.py`).
- The log is encrypted on the device (`homelog/logbook.py`); the key lives in `~/.homelog/key`.
- Flags come from deterministic routine checks (`homelog/routine.py`), so a small summary model cannot miss or invent them.
- HomeLog makes no medical claims. It reports changes in routine.

## Quick start (macOS)

```bash
# 1. Models (Ollama: https://ollama.com/download, or `brew install ollama`)
ollama serve                 # skip if the Ollama app is already running
ollama pull qwen3-vl:2b
ollama pull qwen3:1.7b

# 2. Python
cd homelog
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 3. Run a simulated day
python run_day.py            # English
python run_day.py --lang zh-TW
python run_day.py --backend stub   # plumbing test without models (placeholder text)

# 4. Demo page (replays the real output in sync with the clips)
open -a "Google Chrome" demo/index.html
```

`run_day.py` prints each log line as it is produced, the checked facts, the summary and the average time per frame, and writes `demo/data/day.json` (+ `day.js`) for the demo page. The demo page marks stub output with a large "STUB OUTPUT" watermark.

If `qwen3-vl:2b` is not available in your Ollama version, `qwen2.5vl:3b` works as a drop-in; change `vlm.model` in `config.yaml`.

## Building a day

`scenarios/demo_day.yaml` stitches clips into a day:

```yaml
segments:
  - {type: video, clock: "07:40", span_minutes: 20, file: samples/etri/etri_1.mp4, label: "Living room"}
  - {type: idle,  from: "10:50", to: "16:00"}
```

- `clock`: the time the clip stands for. `span_minutes`: how much of the day it represents.
- `idle`: a stretch with no motion. The trigger stays quiet and the VLM never runs.
- `routine`: meal windows and the inactivity limit the family sets.

Add your own recordings under `samples/own/` and list them as segments. A live camera works too: pass the device index as `file` (for example `"0"`).

## Footage and licenses

- The default scenario uses ETRI-Activity3D sample videos (ETRI). Faces are blurred by the dataset authors. The footage is **not** included in this repository; download it from the dataset authors and place the RGB clips in `samples/etri/` as `etri_1.mp4`, `etri_24.mp4`, `etri_29.mp4`. Ask the authors before showing it publicly.
- Check each model's license before commercial use.
- `.gitignore` excludes all footage, logs, keys and demo data.

## Repository layout

```
homelog/            pipeline: frames, trigger, prompts, backends, log, routine checks
scenarios/          day definitions
demo/index.html     recording-ready demo page
run_day.py          entry point
config.yaml         models, language, sampling
```

## Roadmap

1. Stage II: port the trigger and both models to the UGen300; report laptop vs UGen300 latency and power side by side.
2. Field trial with volunteer households.
3. Multi-room logs, then a companion care robot that uses the same text log to check in on the elder.
