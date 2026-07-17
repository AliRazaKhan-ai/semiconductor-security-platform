from __future__ import annotations
ALLOWED_TRANSITIONS={
 'RAW': {'TEST_UNLOCKED0'}, 'TEST_UNLOCKED0': {'TEST_LOCKED0'}, 'TEST_LOCKED0': {'DEV','PROD'},
 'DEV': {'PROD','RMA'}, 'PROD': {'PROD_END','RMA'}, 'PROD_END': {'RMA'}, 'RMA': set()
}
def transition_allowed(current: str, requested: str) -> bool:
    return requested.upper() in ALLOWED_TRANSITIONS.get(current.upper(), set())
