from app.tts import synthesize

audio_file = synthesize(
    "Hello. This is a test of the Northstar Company voice assistant."
)

print(f"Generated: {audio_file}")