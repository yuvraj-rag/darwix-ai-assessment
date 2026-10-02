from app.agent import answer_question


def main():
    print("Q1 Text Agent")
    print("Type 'exit' to quit.\n")

    while True:
        question = input("You: ").strip()

        if question.lower() == "exit":
            break

        if not question:
            continue

        result = answer_question(question)

        print(f"\nAssistant: {result['answer']}")
        print(f"Latency: {result['latency']}")
        print()


if __name__ == "__main__":
    main()