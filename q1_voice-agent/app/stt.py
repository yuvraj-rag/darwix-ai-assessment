from faster_whisper import WhisperModel

MODEL_SIZE = "medium"

_model = WhisperModel(
    MODEL_SIZE,
    device="cpu",
    compute_type="int8",
)


def transcribe(audio_path: str) -> str:
    segments, _ = _model.transcribe(
        audio_path,
        beam_size=1,
        vad_filter=True,
    )

    text = " ".join(
        segment.text.strip()
        for segment in segments
    ).strip()

    return text