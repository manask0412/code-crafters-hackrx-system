# app/services/retrieval.py
from app.services.embeddings import pinecone_indexes, NAMESPACE

async def search_chunks(query: str, doc_url: str, top_k: int = 5) -> list[str]:
    index = pinecone_indexes["dense"]

    # Construct the search query
    search_query = {
        "inputs": {"text": query},
        "top_k": top_k,
    }

    # Add optional metadata filter (e.g. by doc_url)
    if doc_url:
        search_query["filter"] = {"doc_url": doc_url}

    # Perform search
    resp = await index.search(
        namespace=NAMESPACE,
        query=search_query,
        fields=["text", "doc_url"]
    )

    hits = resp.get("result", {}).get("hits", [])
    if not hits:
        return []

    # Extract matched text chunks
    texts = []
    for hit in hits:
        fld = hit.get("fields", {})
        txt = fld.get("text") or fld.get("chunk_text")
        if txt:
            texts.append(txt)
    return texts
