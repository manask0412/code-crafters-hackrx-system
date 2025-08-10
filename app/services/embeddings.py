# app/services/embeddings.py
from pinecone import Pinecone
from app.core.config import PINECONE_API_KEY, PINECONE_INDEX_NAME, DENSE_INDEX_HOST_URL

NAMESPACE = "hackrx"
pinecone_indexes = {}

async def init_pinecone():
    pc = Pinecone(api_key=PINECONE_API_KEY)
    pinecone_indexes["dense"] = pc.IndexAsyncio(DENSE_INDEX_HOST_URL)
    #logger.info("Pinecone async index initialized.")

async def close_pinecone():
    await pinecone_indexes["dense"].close()
    #logger.info("Pinecone index connection closed.")

async def upsert_chunks(chunks: list[dict], source_url: str):
    index = pinecone_indexes["dense"]
    records = [{"id": c["id"], "text": c["text"],"doc_url": source_url} for c in chunks]
    MAX_BATCH = 96
    for i in range(0, len(records), MAX_BATCH):
        batch = records[i:i + MAX_BATCH]
        await index.upsert_records(namespace=NAMESPACE, records=batch)