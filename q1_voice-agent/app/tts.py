from pathlib import Path
import shutil
import subprocess
import uuid

ROOT = Path(__file__).resolve().parent.parent
TTS_DIR = ROOT / "generated_audio"
TTS_DIR.mkdir(exist_ok=True)

VOICE_MODEL = "en_US-lessac-medium.onnx"


def _find_voice_model() -> Path | None:
    search_dirs = [
        ROOT,
        Path.home() / "AppData" / "Local" / "piper" / "voices",
        Path.home() / ".local" / "share" / "piper" / "voices",
        Path.home() / "piper" / "voices",
    ]

    for base in search_dirs:
        candidate = base / VOICE_MODEL
        if candidate.exists():
            return candidate

    for match in Path.home().rglob(VOICE_MODEL):
        return match

    return None


def synthesize(text: str) -> str | None:
    if shutil.which("piper") is None:
        return None

    model = _find_voice_model()
    if model is None:
        return None

    output_file = TTS_DIR / f"{uuid.uuid4().hex}.wav"

    try:
        subprocess.run(
            [
                "piper",
                "--model",
                str(model),
                "--output_file",
                str(output_file),
            ],
            input=text,
            text=True,
            check=True,
            capture_output=True,
        )
    except (subprocess.CalledProcessError, OSError):
        return None

    return str(output_file)