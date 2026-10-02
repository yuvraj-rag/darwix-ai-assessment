import os
import tempfile
from pathlib import Path

from fastapi import FastAPI, File, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.agent import answer_audio, answer_question
from app.stt import transcribe
from app.tts import synthesize


PROJECT_ROOT = Path(__file__).resolve().parent.parent
FRONTEND_PATH = PROJECT_ROOT / "frontend" / "index.html"
AUDIO_DIR = PROJECT_ROOT / "generated_audio"

app = FastAPI(title="Q1 Voice Agent")


class AskRequest(BaseModel):
    question: str


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/")
def home():
    return FileResponse(str(FRONTEND_PATH))


@app.post("/transcribe")
async def transcribe_audio(audio: UploadFile = File(...)):
    suffix = os.path.splitext(audio.filename or "")[1] or ".webm"

    with tempfile.NamedTemporaryFile(
        delete=False,
        suffix=suffix,
    ) as temp:
        temp.write(await audio.read())
        audio_path = temp.name

    try:
        transcript = transcribe(audio_path)

        return {
            "transcript": transcript,
        }

    finally:
        os.unlink(audio_path)


@app.post("/ask")
def ask(request: AskRequest):
    result = answer_question(request.question)

    answer = result.get("answer", "").strip()

    if answer:
        try:
            audio_path = synthesize(answer)
            if audio_path:
                filename = os.path.basename(audio_path)
                result["audio_url"] = f"/audio/{filename}"
                result["tts_available"] = True
            else:
                result["tts_available"] = False
                result.pop("audio_url", None)
        except Exception:
            result["tts_available"] = False
            result.pop("audio_url", None)

    return result


@app.get("/audio/{filename}")
def get_audio(filename: str):
    audio_path = AUDIO_DIR / filename

    if not audio_path.exists():
        return {
            "error": "Audio file not found."
        }

    return FileResponse(
        str(audio_path),
        media_type="audio/wav",
    )


@app.post("/voice")
async def voice(audio: UploadFile = File(...)):
    suffix = os.path.splitext(audio.filename or "")[1] or ".webm"

    with tempfile.NamedTemporaryFile(
        delete=False,
        suffix=suffix,
    ) as temp:
        temp.write(await audio.read())
        audio_path = temp.name

    try:
        return answer_audio(audio_path)

    finally:
        os.unlink(audio_path)

