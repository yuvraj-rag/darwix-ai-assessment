import requests


Q2_URL = "http://localhost:8000"
TIMEOUT_SECONDS = 10


class RetrievalError(Exception):
    """Raised when the Q2 knowledge base cannot be reached."""


def retrieve_evidence(query: str, top_k: int = 5) -> list[dict]:
    try:
        response = requests.post(
            f"{Q2_URL}/retrieve",
            json={
                "query": query,
                "top_k": top_k,
            },
            timeout=TIMEOUT_SECONDS,
        )

        response.raise_for_status()

        data = response.json()

        return data.get("results", [])

    except requests.exceptions.Timeout as exc:
        raise RetrievalError(
            "The knowledge base is taking too long to respond. "
            "Please try again in a moment."
        ) from exc

    except requests.exceptions.ConnectionError as exc:
        raise RetrievalError(
            "The knowledge base is currently unavailable. "
            "Please try again in a moment."
        ) from exc

    except requests.exceptions.RequestException as exc:
        raise RetrievalError(
            f"The knowledge base returned an error: {exc}"
        ) from exc