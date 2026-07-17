from app.ai.risk_engine.policy_fusion import fuse
def test_mandatory_failure_forces_critical():
 score,reasons=fuse(.05,.02,.03,{"puf_authenticated":False,"opentitan_verified":True,"digital_twin_verified":True,"compliance_passed":True}); assert score>=.95; assert reasons
