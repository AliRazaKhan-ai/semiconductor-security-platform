from app.compliance.common import canonical_hash


class PolicyEngine:
 def __init__(self,c:dict):self.c=c
 def decide(self,e:dict,s:dict,ai:dict)->dict:
  a=ai.get("decision",ai); ar=float(a.get("risk_score",1)); ac=float(a.get("confidence_score",0)); sr=float(s.get("risk_score",1)); ed=e.get("decision","HOLD"); reasons=[]
  if ed=="DENIED" or ar>=self.c["thresholds"]["deny_ai_risk"]: d,st="DENIED","FAILED"; reasons.append("Export denial or critical AI risk")
  elif ed=="LICENSE_REQUIRED": d,st="LICENSE_REQUIRED","HOLD"; reasons.append("License required")
  elif sr>=self.c["thresholds"]["hold_supplier_risk"]: d,st="HOLD","HOLD"; reasons.append("Supplier risk too high")
  elif ac<self.c["thresholds"]["minimum_ai_confidence"] or ed=="MANUAL_REVIEW": d,st="MANUAL_REVIEW","HOLD"; reasons.append("Unresolved classification or insufficient AI confidence")
  else:d,st="APPROVED","PASSED";reasons.append("All mandatory gates passed")
  p={"decision":d,"status":st,"confidence":max(0,min(1,(ac+s.get("confidence",.5)+e.get("confidence",.5))/3)),"risk_score":max(ar,sr,1 if d=="DENIED" else .65 if d in {"HOLD","LICENSE_REQUIRED"} else .4 if d=="MANUAL_REVIEW" else 0),"deployment_recommendation":"DEPLOY" if d=="APPROVED" else "BLOCK" if d=="DENIED" else "DO_NOT_DEPLOY_PENDING_REVIEW","requires_human_review":d!="APPROVED","reasons":reasons,"export_control":e,"supplier_risk":s,"ai":a,"policy_version":self.c.get("version","2.0")}
  p["integrity_hash"]=canonical_hash(p);return p
