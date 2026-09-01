from app.blockchain.common.hashing import canonical_json_bytes, provenance_digest, require_sha256


def test_canonical_hash_is_order_independent():
    assert provenance_digest({"b":2,"a":1}) == provenance_digest({"a":1,"b":2})

def test_require_sha256_rejects_invalid():
    try: require_sha256("abc")
    except ValueError: pass
    else: raise AssertionError("invalid hash accepted")
