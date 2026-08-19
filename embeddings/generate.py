"""
Embedding generation module.

Uses sentence-transformers with the paraphrase-multilingual-MiniLM-L12-v2
model to produce 384-dimensional embeddings for ticket text.
"""

from sentence_transformers import SentenceTransformer

MODEL_NAME = "paraphrase-multilingual-MiniLM-L12-v2"

_model = None


def get_model() -> SentenceTransformer:
    """Return a cached SentenceTransformer model instance."""
    global _model
    if _model is None:
        _model = SentenceTransformer(MODEL_NAME)
    return _model


def generate_embedding(text: str) -> list[float]:
    """Generate a 384-dim embedding vector for the given text.

    Args:
        text: The input text to embed.

    Returns:
        A list of 384 floats representing the embedding.
    """
    model = get_model()
    return model.encode(text, normalize_embeddings=True).tolist()


def generate_embeddings_batch(texts: list[str]) -> list[list[float]]:
    """Generate embeddings for a batch of texts.

    Args:
        texts: List of input strings.

    Returns:
        List of embedding vectors.
    """
    model = get_model()
    return model.encode(texts, normalize_embeddings=True, show_progress_bar=True).tolist()
