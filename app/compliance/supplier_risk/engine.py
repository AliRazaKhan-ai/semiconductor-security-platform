from app.compliance.common import clamp


class SupplierRiskEngine:
 def __init__(self,c:dict):
  self.c=c; total=sum(c["weights"].values()); self.w={k:v/total for k,v in c["weights"].items()}
 def evaluate(self,s:dict,ai:dict)->dict:
  a=ai.get("decision",ai); country=str(s.get("country","")).upper()
  f={"country_risk":clamp(self.c.get("country_risk",{}).get(country,s.get("country_risk",.5))),"custody_gap_ratio":clamp(s.get("custody_gap_ratio",0)),"certificate_risk":clamp(s.get("certificate_risk",0)),"sbom_mismatch_ratio":clamp(s.get("sbom_mismatch_ratio",0)),"threat_intel_score":clamp(s.get("threat_intel_score",0)),"counterfeit_history":clamp(s.get("counterfeit_history",0)),"financial_distress":clamp(s.get("financial_distress",0)),"ai_risk":clamp(a.get("risk_score",.5))}
  score=sum(f.get(k,0)*w for k,w in self.w.items()); level="CRITICAL" if score>=.8 else "HIGH" if score>=.6 else "MEDIUM" if score>=.35 else "LOW"
  return {"supplier_id":str(s.get("supplier_id","UNKNOWN")),"supplier_name":str(s.get("name","UNKNOWN")),"risk_score":score,"risk_level":level,"confidence":max(.4,min(1,len([k for k in f if k in s or k=="ai_risk"])/len(f))),"factors":f,"reasons":[f"{k}={v:.2f}" for k,v in sorted(f.items(),key=lambda x:x[1],reverse=True) if v>=.5],"ruleset_version":self.c.get("version","1.0")}
