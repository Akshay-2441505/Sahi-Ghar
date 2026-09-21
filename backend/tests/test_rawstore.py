from sahighar.rawstore import LocalRawStore


def test_rawstore_roundtrip_and_dedupe(tmp_path):
    store = LocalRawStore(tmp_path)
    key = store.put(b"hello")
    assert store.put(b"hello") == key
    assert store.get(key) == b"hello"
    assert len(list(tmp_path.rglob("*.gz"))) == 1
    assert store.put(b"other") != key
