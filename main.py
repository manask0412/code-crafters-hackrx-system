# main.py
from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from typing import List
import os, asyncio, json
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate
from langchain.chains.combine_documents import create_stuff_documents_chain
from langchain_core.documents import Document
from app.services.ingestion import extract_and_embed_chunks
from app.services.retrieval import search_chunks
from app.services.embeddings import init_pinecone, close_pinecone
from app.services.interactive import run_flight_lookup, fetch_secret_token
from app.core.config import API_AUTH_KEY, GOOGLE_API_KEY, JSON_FILE_PATH
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_pinecone()
    yield
    await close_pinecone()

app = FastAPI(title="Code Crafters HackRx RAG API Version 16", lifespan=lifespan)

bearer_scheme = HTTPBearer()

def verify_api_key(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme)
):
    if credentials.credentials != API_AUTH_KEY:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid or missing API key."
        )

class QARequest(BaseModel):
    documents: str
    questions: List[str]

class QAResponse(BaseModel):
    answers: List[str]

@app.get("/")
async def root():
    return {"message": "Code Crafters LLM Query System API is running 🚀"}

@app.post(
    "/api/v16/hackrx/run",
    response_model=QAResponse,
    dependencies=[Depends(verify_api_key)],
    tags=["hackrx"]
)
async def run_hackrx(req: QARequest):
    doc_url = req.documents
    if req.questions and any("flight number" in q.lower() for q in req.questions):
        try:
            flight_number, destination = await run_flight_lookup()
        except Exception as e:
            return QAResponse(answers=[f"Failed to retrieve flight number: {e}" for _ in req.questions])
        answers = [f"Destination: {destination} and Flight Number: {flight_number}" for _ in req.questions]
        return QAResponse(answers=answers)

    if req.questions and any("secret token" in q.lower() for q in req.questions):
        try:
            token = await fetch_secret_token(doc_url)
        except Exception as e:
            return QAResponse(
                answers=[f"Failed to retrieve secret token: {e}" for _ in req.questions]
            )

        answers = [f"Secret Token: {token}" for _ in req.questions]
        return QAResponse(answers=answers)

    if os.path.exists(JSON_FILE_PATH):
        with open(JSON_FILE_PATH, "r", encoding="utf-8") as f:
                processed_docs = json.load(f)
    else:
        processed_docs = []

    if doc_url not in processed_docs:
        await extract_and_embed_chunks(doc_url)
        processed_docs.append(doc_url)
        with open(JSON_FILE_PATH, "w", encoding="utf-8") as f:
            json.dump(processed_docs, f, indent=4, ensure_ascii=False)

    llm = ChatGoogleGenerativeAI(
        model="gemini-2.5-flash", temperature=0.3, max_tokens=4500
    )

    prompt = ChatPromptTemplate.from_messages([
    ("system", 
     "You are a highly accurate document question-answering assistant that provides precise, single-sentence responses strictly based on the provided context.\n"

     "CORE PRINCIPLES:\n"
     "• Answer ONLY using information from the provided document context\n"
     "• If information is not in the context, state: 'The document does not specify [specific detail]'\n"
     "• Never use general knowledge or external information\n"
     "• Always cite specific clauses, articles, or sections when available\n\n"
     
     "RESPONSE STRUCTURE:\n"
     "• Start with direct Yes/No/specific answer when applicable\n"
     "• Include exact values: amounts (Rs. X), percentages (X%), ages (X years), timeframes\n"
     "• Reference specific sources: Article X, Clause Y.Z, Section A.B, page numbers\n"
     "• Add essential conditions using 'subject to', 'provided that', 'as per'\n"
     "• For multi-part questions: address each component in sequence\n\n"
     
     "INFORMATION HANDLING:\n"
     "• Extract exact values, limits, and conditions from context\n"
     "• When document mentions partial information, present what is available\n"
     "• For missing information, use standardized language: 'The document does not specify [detail]'\n"
     "• Avoid assumptions or interpretations beyond what's explicitly stated\n\n"
     
     "DOMAIN-SPECIFIC RESPONSES:\n"
     "Insurance Claims: State coverage status, exact monetary limits, waiting periods, exclusions, required documents\n"
     "Constitutional Law: Cite specific articles, mention exact provisions, reference constitutional rights\n"
     "Technical Manuals: Provide precise specifications, measurements, safety guidelines, model details\n"
     "Legal Documents: Reference specific sections, clauses, procedures, eligibility criteria\n\n"
     
     "MULTI-PART QUESTION PROTOCOL:\n"
     "• Address each question component systematically\n"
     "• Use semicolons to separate responses to different parts\n"
     "• Maintain document references for each component\n"
     "• If any part lacks information, specify which component is not covered\n\n"
     
     "ETHICAL BOUNDARIES:\n"
     "For requests involving fraud, illegal activities, sensitive information, or harmful actions: State 'No' clearly, explain serious consequences from document context, redirect to legitimate alternatives.\n\n"
     
     "CRITICAL FORMATTING RULES:\n"
     "• Single flowing sentence with no line breaks or bullet points\n"
     "• Maximum 100 words to ensure conciseness and readability\n"
     "• Include all relevant numbers, dates, conditions, and source references\n"
     "• Use professional, factual tone without excessive qualifications\n"
     "• End document limitation statements only when information is genuinely missing\n"
     "• Replace forward slashes with appropriate words: use 'or' instead of '/' (e.g., 'Company or TPA' not 'Company/TPA')\n"
     "• Write currency amounts without trailing slashes: 'Rs. 40,000' not 'Rs. 40,000/-'\n"
     "• Use clean, natural language without escaped characters or technical formatting\n\n"
     
     "QUALITY CHECKLIST:\n"
     "Before responding, verify:\n"
     "1. Answer directly addresses the question asked\n"
     "2. All information comes from provided context\n"
     "3. Specific clause/article references are included\n"
     "4. Response is under 100 words\n"
     "5. Multi-part questions are fully addressed\n\n"
     
     "Context:\n{context}\n\n"),
     ("human", "{input}")])
    doc_chain = create_stuff_documents_chain(llm, prompt)


    # 3️⃣ answer in parallel
    async def get_answer(q: str, doc_url: str, top_k: int = 5):
        top_chunks = await search_chunks(q, doc_url=doc_url, top_k=top_k)
        docs = [Document(page_content=chunk) for chunk in top_chunks]
        resp = await doc_chain.ainvoke({"input": q, "context": docs})
        return q, resp.strip()

    # Run all questions in parallel
    tasks = [get_answer(q, doc_url=req.documents, top_k=10) for q in req.questions]
    results = await asyncio.gather(*tasks)

    answer_texts = [a for (_, a) in results]
    return QAResponse(answers=answer_texts)
