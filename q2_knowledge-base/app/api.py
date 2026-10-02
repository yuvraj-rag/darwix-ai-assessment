from fastapi import FastAPI
from pydantic import BaseModel

from app import vector_store


app = FastAPI(title="Q2 Knowledge Base API")


class RetrievalRequest(BaseModel):
    query: str
    top_k: int = 5


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/retrieve")
def retrieve(request: RetrievalRequest):
    results = vector_store.retrieve(
        request.query,
        top_k=request.top_k,
    )

    return {
        "query": request.query,
        "results": results,
    }