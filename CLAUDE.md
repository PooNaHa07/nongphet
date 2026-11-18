# CLAUDE.md — น้องเพชร AI Smart Guide (PBPVC)

Guidance for AI coding assistants working on **น้องเพชร AI Smart Guide**, a robot kiosk by
วิทยาลัยอาชีวศึกษาเพชรบุรี (abbreviation **PBPVC**), entered in the สอศ. innovation competition.

---

## 1. Project Overview

- **Dual screen on one Flask app (port 5000)**
  - `/kiosk`: 10.1" touch screen (chat, RAG knowledge, voice, Thai Sign Language, tourism info).
  - `/emotion`: animated avatar (eyes, lip-sync, gaze follow).
- **Vision daemon (port 5002, `vision_daemon.py`)**: OpenCV YuNet face landmarks, attention gating, MJPEG stream.
- **ESP32 / arm**: `esp32_listener.py`, `services/arm_service.py`, `routes/arm.py` (servo arm, works before hardware is attached).
- **AI engine (no Gemini, no cloud LLM)**: ML intent classifier + semantic RAG over `knowledge_base.json`
  + optional local SLM (`local_slm.py`, Ollama) + deterministic offline fallback.
- **Voice (one voice for the whole system)**: OmniVoice clone of the Mali reference voice, generated on a
  GPU laptop in the booth (`tools/voice_server.py`, port 8010) and pre-baked into `static/audio/cache/`.
- **Offline-ready pages**: all web libraries are served from `static/vendor/` (no CDN). Only browser speech
  recognition still needs internet.

---

## 2. Directory & Module Structure

```text
d:\nongphet\
├── app.py / app_new.py         # Flask entry point (port 5000) / compatibility wrapper
├── vision_daemon.py            # Vision daemon & MJPEG streamer (port 5002)
├── esp32_listener.py           # ESP32 serial bridge
├── config.py / state.py        # Config from .env / shared in-memory state
├── intent_classifier.py        # Scikit-learn intent classifier
├── semantic_retriever.py       # TF-IDF RAG retriever with hot reload
├── local_slm.py                # Optional local SLM (Ollama)
├── prebake_tts.py              # Bake KB answers + fallback phrases into the voice cache
├── train_intent.py             # Retrain intent classifier
├── knowledge_base.json         # Master knowledge base
├── gunicorn.conf.py            # Pi: 1 worker, threads (state is in-process)
│
├── routes/                     # chat, vision, media (/tts), iot (SSE), admin, display, knowledge, arm
├── services/
│   ├── tts_service.py          # Voice chain, canonical cache guard, speech text prep
│   ├── voice_server_client.py  # Pi side: calls the booth OmniVoice server
│   ├── azure_speech.py         # Optional Azure Speech (edge mode only)
│   ├── knowledge_service.py / knowledge_manager.py / analytics_service.py
│   ├── arm_service.py          # Servo arm control
│   └── text_utils.py
│
├── tools/
│   ├── voice_server.py         # OmniVoice server on the booth GPU laptop (.venv-voice)
│   ├── omnivoice_fast.py       # Faster CFG decoding patch (~20-25%)
│   ├── pick_seed.py            # Audition seeds for a stable voice tone
│   ├── fetch_vendor.py         # Download pinned web libraries into static/vendor/
│   └── fetch_college_data.py / build_college_kb.py   # College data from official PBPVC sources
│
├── docs/                       # Guides (Pi 5 hardware, arm, SSH deploy, system overview) + research_report/
├── voices/                     # Reference voice (audio/text/.pt are git-ignored, see voices/README.md)
├── data/college_official.json  # Scraped official college data
├── static/
│   ├── js/                     # main.js, chat.js, emotion.js, modals.js, sign_language.js, ...
│   ├── vendor/                 # Tailwind, Font Awesome, fonts, MediaPipe Hands, Chart.js, qrcode
│   ├── img/places/             # Place photos (credits in CREDITS.md)
│   └── audio/cache/            # Pre-baked voice cache (MP3 24 kHz 48 kbps mono only)
├── templates/                  # kiosk, emotion, dashboard, knowledge_admin, share, tts_preview
└── tests/                      # Automated test suite (run_tests.py)
```

---

## 3. Commands

```powershell
# Run everything (Windows)
.\run.ps1

# Raspberry Pi 5
./start_kiosk.sh

# Tests: always run after changes, all must pass
.\.venv\Scripts\python.exe run_tests.py

# Booth voice server (GPU laptop, separate venv)
.\.venv-voice\Scripts\python.exe tools\voice_server.py --port 8010

# Bake the voice cache (needs the voice server reachable)
.\.venv\Scripts\python.exe prebake_tts.py

# Refresh offline web libraries
.\.venv\Scripts\python.exe tools\fetch_vendor.py
```

---

## 4. Architectural Rules

### A. Vision & attention gating
- Greet only when attention score ≥ 0.58, |yaw| ≤ 22°, held for ≥ 2 frames.
- Never greet again while `is_person_engaged = True`.
- No face for > 4.0 s → send `user_left` to `/api/iot/trigger` to reset the session.
- Kill orphaned `vision_daemon.py` before starting the camera (Windows DirectShow lock).

### B. Voice (one voice, half-duplex)
- **One voice only**: never fall back to a different voice. If the voice is unavailable, speak the baked
  fallback phrase ("น้องเพชรสรุปคำตอบไว้บนหน้าจอแล้วนะคะ...") and show the text.
- Voice chain (`TTS_ENGINE=omnivoice`):
  1. Baked cache (`static/audio/cache/`), keys from `speech_cache_key` and `VOICE_ID`.
  2. Booth OmniVoice server (`VOICE_SERVER_URL`, `VOICE_SERVER_TOKEN`).
  3. Baked fallback phrase, then text only.
- Kiosk playback: whole answer from cache first (`cache_only`), otherwise sentence by sentence with a short
  prebuffer so speech stays continuous.
- OmniVoice settings: 32 steps live and bake, fixed `OMNIVOICE_SEED`, audio tokenizer on CPU for 4 GB GPUs.
  Changing the reference voice or seed requires a new `VOICE_ID` and a re-bake.
- Keep the mic off while speaking (`isSpeakingTTS`), cooldown 350-500 ms after speech, allow barge-in.

### C. Chat pipeline
1. Intent classifier (< 5 ms).
2. Semantic RAG over `knowledge_base.json` (verified local answers).
3. Optional local SLM (Ollama) for open questions.
4. Deterministic offline fallback.

### D. College data
- Use the abbreviation **PBPVC**. Official sources: pbpvc.ac.th and facebook.com/PBPVC.
- Admission dates and documents must add "โปรดตรวจสอบกับวิทยาลัย".

### E. Persona
- Friendly, polite young lady "น้องเพชร". End Thai sentences with "ค่ะ" / "นะคะ", never "ครับ".
- Spoken style (เขียนเพื่อการฟัง), with 2-3 follow-up suggestion chips.

---

## 5. Security & Configuration

- Secrets in `.env` only (`SECRET_KEY`, `ADMIN_PIN`, `VOICE_SERVER_TOKEN`, optional Azure keys). Never commit it.
- Keep `.env`, logs, `*.bak`, virtualenvs, `voices/` recordings and `voice_samples/` out of git.
- Reconfigure stdout to UTF-8 in entry points and scripts.
- Ports: `5000` Flask, `5002` vision daemon, `8010` booth voice server, `11434` Ollama (optional).
