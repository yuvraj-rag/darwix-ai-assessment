import sys

from app.agent import answer_audio


def main():
    if len(sys.argv) != 2:
        print("Usage: python -m app.audio_cli <audio_file>")
        return

    audio_path = sys.argv[1]

    result = answer_audio(audio_path)

    print("\nTranscript:")
    print(result["transcript"])

    print("\nAssistant:")
    print(result["answer"])

    print("\nSources:")
    for source in result["sources"]:
        print(source)

    print("\nLatency:")
    print(result["latency"])


if __name__ == "__main__":
    main()