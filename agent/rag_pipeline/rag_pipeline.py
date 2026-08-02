"""
Exercise — Retrieval-Augmented Generation Pipeline (§5)
========================================================

Build a complete RAG pipeline from scratch using only the Gemini SDK and
Python's stdlib. No vector database, no LangChain — just math and lists.

Run from the project root:
    python -m rag_pipeline.rag_pipeline

Learning goals:
    - Understand chunking strategies and their trade-offs (§5.2)
    - Generate embeddings with the Gemini text-embedding-004 model (§5.3)
    - Build a vector store using cosine similarity — see exactly how it works (§5.4)
    - Inject retrieved context into an LLM prompt (§5.6)
    - Measure retrieval quality with Precision@k (§5.9)

Key insight: a "vector database" is just a list of (embedding, metadata) pairs
with a similarity search function. The magic is in the embeddings, not the DB.
"""

import math
import re
from dataclasses import dataclass, field

from shared.config import SETTINGS
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from shared.config import get_llm
from shared.config import get_embedder

DIVIDER = "─" * 65
THICK = "═" * 65

EMBEDDING_MODEL = "models/text-embedding-004"


# ─────────────────────────────────────────────────────────────────────────────
# DATA CLASSES
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class Chunk:
    """A slice of a source document with its provenance."""
    text: str
    doc_id: str
    chunk_index: int
    metadata: dict = field(default_factory=dict)


@dataclass
class EmbeddedChunk:
    """A Chunk paired with its embedding vector."""
    chunk: Chunk
    embedding: list[float]


@dataclass
class SearchResult:
    """A retrieved chunk with its similarity score."""
    chunk: Chunk
    score: float


# ─────────────────────────────────────────────────────────────────────────────
# ── §5.2  CHUNKING STRATEGIES
# Chunking determines what goes into each vector — it is one of the biggest
# levers for retrieval quality.
# ─────────────────────────────────────────────────────────────────────────────

# TODO: Implement two chunking strategies.
# chunk_fixed: split text into fixed-size word windows with optional overlap.
#   Overlap prevents a key sentence from being split with no context on either side.
# chunk_sentences: split on sentence boundaries and group max_sentences per chunk.
#   More coherent — sentences are the natural unit of meaning.


def chunk_fixed(text: str, doc_id: str, size: int = 150, overlap: int = 20) -> list[Chunk]:
    """
    Split text into fixed-size word chunks with overlap.

    size    — target word count per chunk
    overlap — number of words shared between adjacent chunks
    """
    words = text.split()
    chunks: list[Chunk] = []
    step = max(1, size - overlap)
    for i, start in enumerate(range(0, len(words), step)):
        chunk_words = words[start: start + size]
        if not chunk_words:
            break
        chunks.append(Chunk(
            text=" ".join(chunk_words),
            doc_id=doc_id,
            chunk_index=i,
            metadata={"strategy": "fixed", "start_word": start},
        ))
    return chunks


def chunk_sentences(text: str, doc_id: str, max_sentences: int = 3) -> list[Chunk]:
    """
    Split text on sentence boundaries and group max_sentences per chunk.
    Sentence boundaries detected by '. ', '! ', '? ', or end-of-string.
    """
    # Split on sentence-ending punctuation followed by a space or end
    raw_sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    sentences = [s.strip() for s in raw_sentences if s.strip()]

    chunks: list[Chunk] = []
    for i, start in enumerate(range(0, len(sentences), max_sentences)):
        group = sentences[start: start + max_sentences]
        chunks.append(Chunk(
            text=" ".join(group),
            doc_id=doc_id,
            chunk_index=i,
            metadata={"strategy": "sentences", "sentence_start": start},
        ))
    return chunks


# ─────────────────────────────────────────────────────────────────────────────
# ── §5.3  EMBEDDING GENERATION
# Embeddings turn text into vectors so we can measure semantic similarity.
# We use Gemini's text-embedding-004 — the same model for both indexing and
# query time (they must match!).
# ─────────────────────────────────────────────────────────────────────────────

# TODO: Implement embed_texts.
# Use client.models.embed_content(model=EMBEDDING_MODEL, contents=texts).
# The response has .embeddings — a list of ContentEmbedding objects.
# Each ContentEmbedding has a .values attribute that is a list[float].


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Embed a batch of texts using text-embedding-004."""
    embedder = get_embedder()
    return embedder.embed_documents(texts)


# ─────────────────────────────────────────────────────────────────────────────
# ── §5.4  IN-MEMORY VECTOR STORE + COSINE SIMILARITY
# The "vector database" is just a Python list. The search is a brute-force
# scan. For teaching this is perfect — you see every step.
# ─────────────────────────────────────────────────────────────────────────────

# TODO: Implement cosine_similarity and VectorStore.
# cosine_similarity: cos(a,b) = dot(a,b) / (|a| * |b|). Use stdlib math only.
# VectorStore: add EmbeddedChunks; search by computing cosine against every
# stored vector and returning top_k sorted by descending score.


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between two vectors using only stdlib math."""
    dot = math.fsum(x * y for x, y in zip(a, b))
    mag_a = math.sqrt(math.fsum(x * x for x in a))
    mag_b = math.sqrt(math.fsum(x * x for x in b))
    if mag_a == 0.0 or mag_b == 0.0:
        return 0.0
    return dot / (mag_a * mag_b)


class VectorStore:
    """
    Pure Python in-memory vector store.

    In production you'd use HNSW or IVF indexing for sub-linear search.
    Here we use brute-force O(n) scan — fine for teaching with < 1,000 chunks.
    """

    def __init__(self) -> None:
        self._store: list[EmbeddedChunk] = []

    def add(self, embedded_chunks: list[EmbeddedChunk]) -> None:
        """Append embedded chunks to the store."""
        self._store.extend(embedded_chunks)

    def search(self, query_embedding: list[float], top_k: int = 3) -> list[SearchResult]:
        """
        Brute-force cosine search — compute similarity against every stored vector.
        Returns top_k results sorted by descending similarity score.
        """
        scores = [
            SearchResult(chunk=ec.chunk, score=cosine_similarity(query_embedding, ec.embedding))
            for ec in self._store
        ]
        scores.sort(key=lambda r: r.score, reverse=True)
        return scores[:top_k]

    def __len__(self) -> int:
        return len(self._store)


# ─────────────────────────────────────────────────────────────────────────────
# ── §5.9  RETRIEVAL METRICS
# Numbers matter: you need to measure whether your retrieval is actually good.
# ─────────────────────────────────────────────────────────────────────────────

# TODO: Implement precision_at_k.
# Precision@k = (number of relevant chunks in top-k) / k
# A chunk is "relevant" if its doc_id is in the relevant_ids set.


def precision_at_k(results: list[SearchResult], relevant_ids: set[str], k: int) -> float:
    """
    Precision@k: what fraction of the top-k retrieved chunks are relevant?
    relevant_ids — set of doc_ids that are ground-truth relevant for the query.
    """
    if k == 0:
        return 0.0
    top_k = results[:k]
    relevant_count = sum(1 for r in top_k if r.chunk.doc_id in relevant_ids)
    return relevant_count / k


# ─────────────────────────────────────────────────────────────────────────────
# LLM HELPER
# ─────────────────────────────────────────────────────────────────────────────

def llm(system: str, messages: list[dict], max_tokens: int = 512, temperature: float = 0.1) -> str:
    """Single LLM call. messages = [{role, content}, ...]"""
    chat = get_llm(temperature=temperature, max_tokens=max_tokens)
    lc_msgs: list = [SystemMessage(content=system)] if system else []
    for m in messages:
        if m["role"] == "user":
            lc_msgs.append(HumanMessage(content=m["content"]))
        else:
            lc_msgs.append(AIMessage(content=m["content"]))
    return chat.invoke(lc_msgs).content.strip()


# ─────────────────────────────────────────────────────────────────────────────
# ── §5  RAG PIPELINE ORCHESTRATOR
# Ties together: chunk → embed → store (index) then embed query → search →
# inject context → generate answer (query).
# ─────────────────────────────────────────────────────────────────────────────

# TODO: Implement RAGPipeline.
# index(documents): chunk each doc → embed all chunks in one batch → store
# query(question): embed question → search → build context → LLM answer


ANSWER_SYSTEM = """You are a helpful assistant. Answer the question using ONLY
the provided context. If the context does not contain enough information, say
"I don't have enough information in the provided context."
Be concise (1-3 sentences)."""


class RAGPipeline:
    """
    End-to-end RAG pipeline backed by a pure-Python vector store.

    index(documents)  → chunk → embed → store
    query(question)   → embed query → similarity search → inject context → LLM answer
    """

    def __init__(self, chunk_strategy: str = "sentences"):
        """
        chunk_strategy: "fixed" or "sentences"
        """
        self.store = VectorStore()
        self.chunk_strategy = chunk_strategy
        self._embedding_dim: int | None = None

    def _chunk(self, text: str, doc_id: str) -> list[Chunk]:
        if self.chunk_strategy == "fixed":
            return chunk_fixed(text, doc_id)
        return chunk_sentences(text, doc_id)

    def index(self, documents: dict[str, str]) -> None:
        """
        Index a dict of {doc_id: text}.
        Steps: chunk each document → embed all chunks in one batch → store.
        """
        all_chunks: list[Chunk] = []
        for doc_id, text in documents.items():
            all_chunks.extend(self._chunk(text, doc_id))

        if not all_chunks:
            return

        print(f"  Embedding {len(all_chunks)} chunks with {EMBEDDING_MODEL}...")
        texts = [c.text for c in all_chunks]
        embeddings = embed_texts(texts)
        self._embedding_dim = len(embeddings[0]) if embeddings else 0

        embedded = [EmbeddedChunk(chunk=c, embedding=e) for c, e in zip(all_chunks, embeddings)]
        self.store.add(embedded)
        print(f"  Done. Embedding dimension: {self._embedding_dim}")

    def query(self, question: str, top_k: int = 3) -> str:
        """
        RAG query:
        1. Embed the question
        2. Similarity search for top_k chunks
        3. Build context string
        4. LLM generates a grounded answer
        """
        query_emb = embed_texts([question])[0]
        results = self.store.search(query_emb, top_k=top_k)

        context = "\n\n".join(
            f"[{r.chunk.doc_id} / chunk {r.chunk.chunk_index}  score={r.score:.3f}]\n{r.chunk.text}"
            for r in results
        )
        prompt = f"Context:\n{context}\n\nQuestion: {question}"
        return llm(ANSWER_SYSTEM, [{"role": "user", "content": prompt}])

    def query_with_metrics(
        self,
        question: str,
        relevant_doc_ids: set[str],
        top_k: int = 3,
    ) -> tuple[str, list[SearchResult], float]:
        """
        Run a query and also compute Precision@k.
        Returns (answer, results, precision_score).
        """
        query_emb = embed_texts([question])[0]
        results = self.store.search(query_emb, top_k=top_k)
        p_at_k = precision_at_k(results, relevant_doc_ids, top_k)

        context = "\n\n".join(
            f"[{r.chunk.doc_id} / chunk {r.chunk.chunk_index}  score={r.score:.3f}]\n{r.chunk.text}"
            for r in results
        )
        prompt = f"Context:\n{context}\n\nQuestion: {question}"
        answer = llm(ANSWER_SYSTEM, [{"role": "user", "content": prompt}])
        return answer, results, p_at_k


# ─────────────────────────────────────────────────────────────────────────────
# DEMO DOCUMENTS  (AcmeCorp knowledge base — entirely in-memory)
# ─────────────────────────────────────────────────────────────────────────────

DEMO_DOCUMENTS = {
    "doc_refunds": (
        "AcmeCorp accepts returns within 30 days of purchase for physical products. "
        "Items must be in original packaging with proof of purchase. "
        "Digital goods are refundable within 14 days if the download has not been initiated. "
        "Refunds are processed within 5 business days to the original payment method. "
        "Shipping costs are non-refundable unless the return is due to our error."
    ),
    "doc_shipping": (
        "Standard shipping is free for orders over $50 within the continental US. "
        "Orders below $50 incur a flat $5.99 shipping fee. "
        "Express shipping is available for $12.99 and delivers within 2 business days. "
        "International shipping is available to 42 countries. "
        "International delivery takes 7 to 14 business days depending on destination. "
        "All orders are trackable via the customer portal."
    ),
    "doc_pricing": (
        "AcmeCorp offers three pricing tiers. "
        "The Free tier costs nothing and includes 5 GB of storage and community forum support. "
        "The Pro tier costs $29 per month and includes 100 GB storage, priority email support, and full API access. "
        "The Enterprise tier is priced by contract and includes unlimited storage, a 99.9% uptime SLA, "
        "dedicated account management, and custom integrations. "
        "Annual billing is available for Pro at $290 per year, saving 2 months."
    ),
    "doc_security": (
        "AcmeCorp encrypts all customer data at rest using AES-256 and in transit using TLS 1.3. "
        "We are SOC 2 Type II certified and GDPR compliant. "
        "Passwords are stored using bcrypt with a work factor of 12. "
        "We perform annual third-party penetration tests and publish the results in our security portal. "
        "Customers can request data deletion within 30 days under GDPR Article 17. "
        "Multi-factor authentication is mandatory for all admin accounts."
    ),
}

DEMO_QUERIES = [
    {
        "question": "How many days do I have to return a digital product?",
        "relevant_ids": {"doc_refunds"},
    },
    {
        "question": "How much does the Pro plan cost per year with annual billing?",
        "relevant_ids": {"doc_pricing"},
    },
    {
        "question": "Is international shipping available and how long does it take?",
        "relevant_ids": {"doc_shipping"},
    },
]


# ─────────────────────────────────────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    print(THICK)
    print("RAG Pipeline Exercise (§5)")
    print(f"Model: {SETTINGS.model}   Embeddings: {EMBEDDING_MODEL}")
    print(THICK)

    # ── §5.2  Show both chunking strategies side-by-side ─────────────────────
    print(f"\n{DIVIDER}")
    print("§5.2  Chunking Strategies (fixed-size vs sentence-boundary)")
    print(DIVIDER)
    sample_doc = DEMO_DOCUMENTS["doc_refunds"]
    fixed_chunks = chunk_fixed(sample_doc, "doc_refunds")
    sent_chunks = chunk_sentences(sample_doc, "doc_refunds")
    print(f"Fixed-size  (150 words, overlap 20):  {len(fixed_chunks)} chunk(s) from doc_refunds")
    print(f"Sentence-boundary (3 sentences/chunk): {len(sent_chunks)} chunk(s) from doc_refunds")
    print(f"\nFixed chunk #0 preview:    \"{fixed_chunks[0].text[:80]}...\"")
    print(f"Sentence chunk #0 preview: \"{sent_chunks[0].text[:80]}...\"")

    # ── §5.3 & §5.4  Index with sentence-boundary strategy ───────────────────
    print(f"\n{DIVIDER}")
    print("§5.3  Embedding Generation  →  §5.4  Building the Vector Store")
    print(DIVIDER)
    print(f"Using sentence-boundary strategy to index {len(DEMO_DOCUMENTS)} documents.")
    pipeline = RAGPipeline(chunk_strategy="sentences")
    pipeline.index(DEMO_DOCUMENTS)
    print(f"VectorStore: {len(pipeline.store)} chunks indexed.")

    # ── §5.6  Query with context injection + §5.9  Retrieval metrics ──────────
    print(f"\n{DIVIDER}")
    print("§5.6  Query (embed → search → inject context → LLM)  +  §5.9  Precision@k")
    print(DIVIDER)

    for i, demo in enumerate(DEMO_QUERIES, 1):
        question = demo["question"]
        relevant = demo["relevant_ids"]
        print(f"\n── Query {i} ──────────────────────────────────────────────────────")
        print(f"Question: \"{question}\"")
        answer, results, p_at_k = pipeline.query_with_metrics(question, relevant, top_k=3)

        print(f"\nTop-3 retrieved chunks:")
        for j, r in enumerate(results, 1):
            print(f"  [{j}] score={r.score:.3f}  {r.chunk.doc_id}  chunk_{r.chunk.chunk_index}  "
                  f"\"{r.chunk.text[:70]}...\"")

        print(f"\nGrounded answer: {answer}")
        print(f"Precision@3 (relevant={relevant}): {p_at_k:.2f}  "
              f"({sum(1 for r in results if r.chunk.doc_id in relevant)} of 3 chunks from correct doc)")

    print(f"\n{THICK}")
    print("Key takeaway: the vector store is just a list + cosine similarity.")
    print("Chunking and embedding model choice matter far more than the DB choice.")
    print(THICK)


if __name__ == "__main__":
    main()
