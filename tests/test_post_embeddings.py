import numpy as np

from heimdall.nlp.post_embeddings import blob_to_vector, resolve_embedding_matrix, vector_to_blob


def test_vector_blob_roundtrip() -> None:
    vec = np.array([0.1, 0.2, 0.3], dtype=np.float32)
    blob = vector_to_blob(vec)
    restored = blob_to_vector(blob, dim=3)
    assert np.allclose(vec, restored)


def test_resolve_embedding_matrix_uses_cache(monkeypatch) -> None:
    calls: list[int] = []

    def fake_encode(texts, **kwargs):
        calls.append(len(texts))
        return np.ones((len(texts), 4), dtype=np.float32), "test-model"

    monkeypatch.setattr("heimdall.nlp.post_embeddings.encode_texts", fake_encode)
    cached = {1: np.array([1, 0, 0, 0], dtype=np.float32), 2: np.array([0, 1, 0, 0], dtype=np.float32)}
    matrix, encoder = resolve_embedding_matrix([1, 2], ["a", "b"], cached=cached, model_name="test")
    assert calls == []
    assert matrix.shape == (2, 4)
    assert encoder == "test"
