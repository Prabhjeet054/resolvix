"""Tests for the embedding generation module."""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from embeddings.generate import generate_embedding, generate_embeddings_batch


class TestEmbeddings(unittest.TestCase):
    """Verify embedding generation produces correct dimensions."""

    def test_single_embedding_dimension(self):
        """A single embedding should be a list of 384 floats."""
        emb = generate_embedding("test query")
        self.assertEqual(len(emb), 384)
        self.assertIsInstance(emb[0], float)

    def test_batch_embeddings(self):
        """Batch generation should return one embedding per input."""
        texts = ["hello", "world", "hola mundo"]
        embs = generate_embeddings_batch(texts)
        self.assertEqual(len(embs), 3)
        for emb in embs:
            self.assertEqual(len(emb), 384)

    def test_multilingual_embedding(self):
        """Embeddings should work for non-English text."""
        emb = generate_embedding("パスワードをリセットしたい")
        self.assertEqual(len(emb), 384)


if __name__ == "__main__":
    unittest.main()
