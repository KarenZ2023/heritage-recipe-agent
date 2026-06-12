"""Recipe RAG API Service.

This module initializes a FastAPI application that serves a Retrieval-Augmented 
Generation (RAG) pipeline for historic cookbook recipes. It exposes an endpoint 
to accept user questions and return AI-generated answers based on the cookbook data.
"""

from fastapi import FastAPI
from pydantic import BaseModel
from scripts.recipe_rag import RecipeRAG

rag = RecipeRAG()

app = FastAPI(
    title="Recipe RAG API",
    description="API endpoint for querying the historic cookbook RAG pipeline.",
)

class QueryRequest(BaseModel):
    """Pydantic model representing the user's API query request."""
    question: str

@app.post("/ask")
def ask_question(request: QueryRequest):
    """Queries the RAG pipeline with a user's question.

    Args:
        request (QueryRequest): The incoming request containing the user's 
            text question.

    Returns:
        dict: A dictionary containing the original question and the 
            generated answer from the RAG pipeline.
    """

    answer = rag.run_rag(request.question)

    return {
        "question": request.question,
        "answer": answer
    }