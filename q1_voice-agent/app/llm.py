import requests


OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL = "qwen2.5:3b"


SYSTEM_PROMPT = """
You are a knowledge-grounded business-loan assistant.

Answer the user's question using ONLY the supplied knowledge-base evidence.

Rules:
- Do not invent facts, policies, requirements, amounts, dates, or procedures.
- If the evidence is insufficient, clearly say that the knowledge base does not contain enough information.
- Give concise, useful answers.
"""


def generate_answer(question: str, evidence: list[dict]) -> str:
    evidence_text = "\n\n".join(
        f"""
SOURCE: {item.get("source", "Unknown")}
VERSION: {item.get("version", "Unknown")}
EFFECTIVE DATE: {item.get("effective_date", "Unknown")}

CONTENT:
{item.get("text", "")}
"""
        for item in evidence
    )

    prompt = f"""
{SYSTEM_PROMPT}

KNOWLEDGE-BASE EVIDENCE:
{evidence_text}

USER QUESTION:
{question}

ANSWER:
"""

    response = requests.post(
        OLLAMA_URL,
        json={
            "model": MODEL,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": 0.1
            },
        },
        timeout=120,
    )

    response.raise_for_status()

    return response.json()["response"].strip()