from app.blockchain.common.hashing import sha256_hex
from app.blockchain.ethereum.merkle import merkle_proof, merkle_root, verify_proof


def test_merkle_proofs_for_odd_leaf_count():
    leaves=[sha256_hex(str(i)) for i in range(5)]
    root=merkle_root(leaves)
    for index, leaf in enumerate(leaves):
        assert verify_proof(leaf, merkle_proof(leaves,index), root)
