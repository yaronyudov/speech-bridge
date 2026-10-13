#!/usr/bin/env bash
# Live Hebrew Transcription Client runner
# Streams microphone audio to the local speech-bridge service,
# displays live transcription in terminal, and appends to transcript.txt.
# Also saves original voice audio to {output_stem}_voice_org.wav.

set -e
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ "$1" == "-h" || "$1" == "--help" ]]; then
    exec "$DIR/.venv/bin/python" "$DIR/examples/mic_live_client.py" --help
fi

OUTPUT_FILE="${1:-transcript.txt}"
STEM="${OUTPUT_FILE%.*}"
AUDIO_FILE="${STEM}_voice_org.wav"
if [ $# -ge 1 ]; then
    shift
fi

echo "========================================================"
echo "🎤 Live Hebrew Transcription"
echo "📄 Text transcript file:   $OUTPUT_FILE"
echo "🎙️  Original voice audio:   $AUDIO_FILE"
echo "🗣️  Speak into your microphone in Hebrew"
echo "🛑 Press Ctrl+C when finished to reconcile & save all"
echo "========================================================"

exec "$DIR/.venv/bin/python" "$DIR/examples/mic_live_client.py" \
    --language he \
    --reconcile \
    -o "$OUTPUT_FILE" \
    "$@"
