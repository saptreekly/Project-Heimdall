from heimdall.datasets.tweet_eval import (
    LABEL_NAMES,
    _normalize_subsets,
    parse_tweet_eval_meta,
)


def test_normalize_subsets_defaults_to_hate():
    assert _normalize_subsets(["immigration"]) == ["hate"]
    assert _normalize_subsets(["hate", "offensive"]) == ["hate", "offensive"]


def test_parse_tweet_eval_meta():
    raw = '{"subset":"hate","label":1,"label_name":"hate","source":"cardiffnlp/tweet_eval"}'
    meta = parse_tweet_eval_meta(raw)
    assert meta is not None
    assert meta["label_name"] == "hate"


def test_hate_labels_binary():
    assert LABEL_NAMES["hate"][1] == "hate"
