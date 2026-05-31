from fastapi import FastAPI
from pydantic import BaseModel
from scripts.recipe_rag import RecipeRAG

rag = RecipeRAG()

app = FastAPI()

class QueryRequest(BaseModel):
    question: str

@app.post("/ask")
def ask_question(request: QueryRequest):

    answer = rag.run_rag(request.question)

    return {
        "question": request.question,
        "answer": answer
    }