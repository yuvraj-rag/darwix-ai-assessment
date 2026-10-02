import time

from app.conversation import (
    ConversationState,
    detect_escalation,
    detect_qualification_intent,
    next_qualification_question,
)
from app.llm import generate_answer
from app.retrieval import retrieve_evidence
from app.stt import transcribe


conversation = ConversationState()


def _base_response(
    question: str,
    answer: str,
    start: float,
    retrieval_ms: float = 0,
    llm_ms: float = 0,
    evidence: list[dict] | None = None,
    escalation: bool = False,
    error: str | None = None,
) -> dict:
    result = {
        "question": question,
        "answer": answer,
        "sources": [
            {
                "source": item.get("source"),
                "record_id": item.get("record_id"),
                "score": item.get("score"),
            }
            for item in (evidence or [])
        ],
        "retrieval_results": evidence or [],
        "qualification": conversation.summary(),
        "escalation": escalation,
        "latency": {
            "retrieval_ms": round(retrieval_ms, 2),
            "llm_ms": round(llm_ms, 2),
            "total_ms": round(
                (time.perf_counter() - start) * 1000,
                2,
            ),
        },
    }

    if error:
        result["error"] = error

    return result


def answer_question(question: str, top_k: int = 5) -> dict:
    start = time.perf_counter()

    conversation.add_turn("user", question)

    # Human escalation takes priority.
    if detect_escalation(question):
        conversation.escalation_requested = True

        answer = (
            "Certainly. I'll arrange for a human representative "
            "to assist you."
        )

        conversation.add_turn("assistant", answer)

        return _base_response(
            question=question,
            answer=answer,
            start=start,
            escalation=True,
        )

    # Start or continue the business-loan qualification flow.
    if detect_qualification_intent(question):
        conversation.qualification_active = True

    if conversation.qualification_active:
        next_question = next_qualification_question(conversation)

        if next_question:
            conversation.add_turn("assistant", next_question)

            return _base_response(
                question=question,
                answer=next_question,
                start=start,
            )

    # Normal knowledge-base question.
    retrieval_start = time.perf_counter()

    try:
        evidence = retrieve_evidence(question, top_k)
    except Exception as exc:
        retrieval_ms = (
            time.perf_counter() - retrieval_start
        ) * 1000

        return _base_response(
            question=question,
            answer=str(exc),
            start=start,
            retrieval_ms=retrieval_ms,
            error="retrieval_unavailable",
        )

    retrieval_ms = (
        time.perf_counter() - retrieval_start
    ) * 1000

    if not evidence:
        answer = (
            "I don't have enough information in the "
            "knowledge base to answer that accurately."
        )

        conversation.add_turn("assistant", answer)

        return _base_response(
            question=question,
            answer=answer,
            start=start,
            retrieval_ms=retrieval_ms,
            error="no_evidence",
        )

    llm_start = time.perf_counter()

    try:
        answer = generate_answer(
            question,
            evidence,
        )
    except Exception as exc:
        llm_ms = (
            time.perf_counter() - llm_start
        ) * 1000

        answer = str(exc)
        conversation.add_turn("assistant", answer)

        return _base_response(
            question=question,
            answer=answer,
            start=start,
            retrieval_ms=retrieval_ms,
            llm_ms=llm_ms,
            evidence=evidence,
            error="llm_unavailable",
        )

    llm_ms = (
        time.perf_counter() - llm_start
    ) * 1000

    conversation.add_turn("assistant", answer)

    return _base_response(
        question=question,
        answer=answer,
        start=start,
        retrieval_ms=retrieval_ms,
        llm_ms=llm_ms,
        evidence=evidence,
    )


def answer_audio(
    audio_path: str,
    top_k: int = 5,
) -> dict:

    stt_start = time.perf_counter()

    transcript = transcribe(audio_path)

    stt_ms = (
        time.perf_counter() - stt_start
    ) * 1000

    if not transcript:
        return {
            "transcript": "",
            "answer": (
                "I couldn't hear any speech. "
                "Please try again."
            ),
            "sources": [],
            "qualification": conversation.summary(),
            "latency": {
                "stt_ms": round(stt_ms, 2),
                "total_ms": round(stt_ms, 2),
            },
            "error": "no_speech",
        }

    result = answer_question(
        transcript,
        top_k,
    )

    result["transcript"] = transcript

    result["latency"]["stt_ms"] = round(
        stt_ms,
        2,
    )

    result["latency"]["total_ms"] = round(
        stt_ms + result["latency"]["total_ms"],
        2,
    )

    return result