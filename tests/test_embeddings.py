from heimdall.nlp.embeddings import encode_texts, neural_embeddings_enabled


def test_neural_embeddings_disabled_uses_tfidf(monkeypatch):
    monkeypatch.setenv("USE_NEURAL_EMBEDDINGS", "false")
    assert neural_embeddings_enabled() is False
    matrix, label = encode_texts(["border crisis election fraud"])
    assert label == "tfidf-fallback"
    assert matrix.shape[0] == 1
