# Hebrew STT & TTS Guide — speech-bridge

Comprehensive guide for running high-accuracy, low-latency Hebrew Speech-to-Text (STT) and Text-to-Speech (TTS) locally and offline.

---

## 1. Executive Summary & Recommended Models

Generic multilingual Whisper models (`tiny`, `base`, `small`, `medium`) struggle with Hebrew grammar, roots, slang, and ambient acoustic conditions in meeting rooms.

For native Hebrew accuracy, use models trained and fine-tuned by **[ivrit-ai](https://huggingface.co/ivrit-ai)**:

| Model | Size | Decoder Layers | Speed on CPU | Best Used For |
|---|---|---|---|---|
| **`ivrit-ai/whisper-large-v3-turbo-ct2`**<br>*(Recommended Default)* | ~1.6 GB | 4 | **~3–4s latency** (Fast) | **Live mic streaming & CPU meeting recording** |
| `ivrit-ai/whisper-large-v3-ct2` | ~3.1 GB | 32 | ~8–12s latency (Slow) | GPU servers & offline batch transcription |

> **Why Turbo?**  
> `whisper-large-v3` has 32 encoder and 32 decoder layers (1.55B parameters). On a CPU, each inference pass takes ~7–9 seconds. `whisper-large-v3-turbo` preserves all 32 encoder layers but reduces the decoder to 4 layers. This makes it **8–10x faster** on CPU while retaining virtually identical Hebrew Word Error Rate (WER).

---

## 2. Library Gotchas & Pre-flight Checklist

Before running, ensure your Python environment meets these exact requirements:

### A. Virtual Environment
Always use the local repository virtualenv:
```bash
source .venv/bin/activate
```
*(If you run system `uvicorn` or `pip`, you may get `zsh: command not found: uvicorn` or missing package errors).*

### B. PyAV Version Incompatibility (`av<14`)
`faster-whisper` depends on `av` (PyAV) for audio decoding. In `av>=14.0.0`, the library removed the `metadata_errors` keyword argument, causing a crash:
```text
TypeError: open() got an unexpected keyword argument 'metadata_errors'
```
**Fix:** Pin `av<14.0.0`:
```bash
pip install "av<14"
```

### C. Microphone Permissions & macOS Input Volume
1. **Privacy Permission**: Ensure your Terminal, iTerm, or IDE has Microphone access in:  
   `System Settings > Privacy & Security > Microphone`.
2. **Input Gain**: Meeting rooms require strong microphone sensitivity so whispered or distant voices are picked up without distortion. Set your input volume to 85%:
   ```bash
   osascript -e "set volume input volume 85"
   ```

### D. Silero VAD in Live Streaming
In live streaming, short rolling chunks (1–2 seconds) can sometimes be falsely classified as silence by Silero VAD if `vad_filter=True` is enabled on small buffers.  
In `speech-bridge`:
- Live rolling chunks use `vad_filter=False` so ongoing speech is never stripped.
- Full-session batch reconciliation uses `vad_filter=True` to eliminate silence hallucinations.

---

## 3. Quickstart: 3-Step Setup

### Step 1: Install Dependencies
```bash
source .venv/bin/activate
pip install -r speech_engine/requirements.txt -r requirements-dev.txt
```

### Step 2: Configure `.env`
Ensure your `.env` contains:
```ini
# Engine selection
STT_ENGINE=local
TTS_ENGINE=local

# Recommended Hebrew model & settings
STT_LOCAL_MODEL_SIZE=ivrit-ai/whisper-large-v3-turbo-ct2
STT_LOCAL_DEVICE=auto
STT_LOCAL_COMPUTE_TYPE=auto
STT_LOCAL_BEAM_SIZE=1

# Live streaming interval
STT_STREAM_INFER_INTERVAL_SECONDS=0.8
STT_STREAM_MIN_CONTEXT_SECONDS=2.0
STT_STREAM_MAX_SEGMENT_SECONDS=10.0
STT_STREAM_SILENCE_RMS_THRESHOLD=130
STT_STREAM_TRAILING_SILENCE_SECONDS=0.8
```

### Step 3: Start the Server
```bash
./start_server.sh
```
The server will warm up the model and display:
```text
INFO: faster-whisper model loaded (cpu_threads=8)
INFO: Application startup complete.
INFO: Uvicorn running on http://0.0.0.0:8000
```

---

## 4. Running Live Hebrew Transcription

In a separate terminal window:
```bash
./run_live_hebrew.sh
```

### What Happens:
1. **Microphone Audio Meter**: Shows live input activity in the terminal:
   ```text
   [mic ▆▆▆▆] Listening (RMS: 350)...
   ```
2. **Live Streaming Text**: As you speak, partial and finalized Hebrew transcriptions appear in real time:
   ```text
   [partial (380ms)] בדיקה
   [partial (410ms)] בדיקה, בדיקה
   [final   (520ms)] בדיקה, בדיקה, שומעים טוב?
   ```
3. **Automatic File Saving**:
   - `transcript.txt`: Contains live text as it is transcribed.
   - `transcript_voice_org.wav`: Stores the 16 kHz uncompressed voice audio of everything spoken.
4. **Clean Exit & Reconciliation**:
   - Press **Ctrl+C** to stop.
   - The script automatically sends the recorded WAV to `/api/v1/transcribe` for a final, high-precision batch reconciliation pass.
   - If you press Ctrl+C a second time during reconciliation, it cancels gracefully without crashing.

---

## 5. Benchmarking & Latency Verification

To verify that your setup is working without needing to speak into the microphone, run the automated latency benchmark:

```bash
./scripts/test_latency.py
```

This script:
1. Synthesizes a test sentence using macOS Carmit voice, or automatically falls back to clean synthetic audio in headless Linux / CI environments (or pass `--synthetic` to force synthetic tone audio).
2. Streams raw 16 kHz PCM chunks over WebSocket to `ws://localhost:8000/api/v1/live-transcribe` (customizable via `--url`).
3. Measures and reports average, minimum, and peak latency for each partial and final transcription event.
4. Pass `--help` to inspect all options:
   ```bash
   ./scripts/test_latency.py --help
   ```

### 5.1 Interactive Comparison & Multi-Model Benchmark (`scripts/`)

A dedicated CLI tool to benchmark all candidate models on your actual audio files:

```bash
# 1. Deliver your own voice interactively (press Enter to start/stop, then auto-benchmark):
./scripts/record_and_test.sh
# or: make record

# 2. Benchmark EVERY model that can suit Hebrew side-by-side on an audio file:
./scripts/compare_hebrew.sh --model all --file my_voice.wav
# or: make benchmark

# 3. Benchmark only the 3 native Ivrit-AI models (Turbo, Large-v3, v2-d4):
./scripts/compare_hebrew.sh --model ivrit --file my_voice.wav

# 4. Compare Turbo vs Large-v3 side-by-side:
./scripts/compare_hebrew.sh --model both --file my_voice.wav

# 5. Test live microphone streaming with Turbo:
./scripts/compare_hebrew.sh --live --model turbo
```

### 5.2 Automatic Right-To-Left (RTL) & Live Audio Meter

RTL layout and sensitivity metering are **automatically integrated**:
- **Continuous Microphone RMS Meter**: The live streaming client calculates signal RMS every 80ms and displays graphical volume bars (`[מיק ▆▆▆█ | RMS: 520]`), giving real-time feedback that the microphone is picking up speech.
- **Low-Latency Sliding Buffer**: Live speech is evaluated every **0.45s** (450ms) with a rolling audio buffer so words appear almost immediately as you speak instead of waiting for long sentence buffers.
- **Correct Hebrew Letter Direction**: Text displayed in terminal emulators has Unicode BiDi shaping (`get_display()`) enabled by default so Hebrew letters read naturally right-to-left.
- **Bracket Tags**: Words inside bracket tags are shaped so they read right-to-left (`[מתמלל 120ms ...]`, `[סופי 120ms ...]`). Pass `--en-tags` if you prefer English technical tags (`[LIVE ...]`, `[FINAL ...]`).
- **File Export**: All files saved to disk (`transcript.txt`) preserve logical Unicode order with `\u200F` (RLM) so text editors and word processors open them in standard Hebrew layout.
- **LTR Override**: Pass `--ltr` if you prefer standard left-aligned terminal output. Pass `--no-bidi` if your terminal already performs hardware BiDi reordering.

---

## 6. Batch Transcription via REST API

To transcribe an existing audio recording (e.g. from a meeting or phone call):

```bash
curl -X POST "http://localhost:8000/api/v1/transcribe?language=he" \
     -F "audio=@transcript_voice_org.wav"
```

Response:
```json
{
  "text": "בדיקה, בדיקה, בדיקה, שומעים טוב."
}
```

---

## 7. Hebrew Text-to-Speech (TTS)

By default, `speech-bridge` uses Microsoft Edge Neural TTS (`TTS_LOCAL_BACKEND=edge`), which provides natural-sounding Hebrew voices (`he-IL-AvriNeural` and `he-IL-HilaNeural`) with zero API keys and zero cost:

```bash
curl -X POST http://localhost:8000/api/v1/synthesize \
     -H "Content-Type: application/json" \
     -d '{"text": "שלום, המערכת מוכנה לפגישה.", "language": "he"}' \
     --output response.mp3
```

---

## 8. Common Troubleshooting

| Issue | Cause | Fix |
|---|---|---|
| `zsh: command not found: uvicorn` | Virtual environment not active | Use `./start_server.sh` or run `source .venv/bin/activate`. |
| No live text flowing during speech | Model too heavy for CPU | Switch to `ivrit-ai/whisper-large-v3-turbo-ct2` in `.env`. |
| Broken syllables ("פאפא", "קבב") during streaming | Whisper forced to infer on < 2s audio | Server now enforces 2.2s minimum acoustic context and Hebrew `initial_prompt`. |
| Left-to-Right (LTR) or flipped punctuation | Terminal BiDi engine lacks Hebrew RTL alignment | Terminal client now uses native Hebrew tags (`[סופי]`, `[מתמלל]`) so the Unicode BiDi algorithm formats the line as RTL. `transcript.txt` includes Right-To-Left marks (`\u200F`). |
| High RAM usage (e.g. 17GB on Activity Monitor) | HuggingFace downloading multi-gigabyte models + OS unified file cache | Server process RSS is steady at ~1.5 GB. Streaming audio buffers are capped at 10s (320 KB). Memory does not leak during long recording sessions. |
