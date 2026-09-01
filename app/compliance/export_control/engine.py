from __future__ import annotations

import json
import re
from pathlib import Path

from rapidfuzz import fuzz

from app.compliance.common import Finding


def norm(v:str)->str:return " ".join(re.sub(r"[^A-Z0-9 ]+"," ",v.upper()).split())

class ExportControlEngine:
 def __init__(self,config:dict,root:Path):self.c=config;self.root=root
 def _screen(self,name:str)->Finding:
  p=self.root/self.c["restricted_parties"]["path"]
  records=[]
  if p.exists(): records=json.loads(p.read_text()).get("results",[])
  best=0.0; hit={}
  for r in records:
   for n in [r.get("name","")]+r.get("aliases",[]):
    s=float(fuzz.WRatio(norm(name),norm(str(n))))
    if s>best:best=s;hit=r
  deny=float(self.c["restricted_parties"]["deny_threshold"]); review=float(self.c["restricted_parties"]["review_threshold"])
  status="MATCH" if best>=deny else "POSSIBLE_MATCH" if best>=review else "CLEAR"
  return Finding("restricted_party",status,min(1,best/100),(f"best fuzzy match {best:.1f}%",),{"matched":hit})
 def evaluate(self,item:dict,tx:dict,parties:dict)->dict:
  tags={str(x).lower() for x in item.get("tags",[])}; end=str(tx.get("end_use","")).lower(); dest=str(tx.get("destination_country","")).upper()
  explicit_usml=str(item.get("usml_category","")).strip(); military=bool(item.get("specially_designed_for_military")) or any(t in end or t in tags for t in self.c["itar"]["military_indicators"])
  itar_status="ITAR_CONTROLLED" if explicit_usml else "POTENTIALLY_ITAR" if military else "NOT_INDICATED"
  itar=Finding("itar",itar_status,1.0 if explicit_usml else .85 if military else .1,("USML/defense indicators evaluated",),{"usml_category":explicit_usml or None})
  eccn=str(item.get("eccn","")).upper(); restricted=dest in self.c["ear"]["restricted_destinations"]; prohibited=any(t in end for t in self.c["ear"]["prohibited_end_use_terms"])
  military_user=any(t in str(tx.get("end_user_type","")).lower() for t in self.c["ear"]["military_end_user_terms"])
  if prohibited: ear_status="PROHIBITED_END_USE"
  elif restricted or military_user: ear_status="LICENSE_REQUIRED"
  elif eccn in self.c["ear"]["controlled_eccns"]: ear_status="LICENSE_REVIEW"
  elif eccn: ear_status="ECCN_REVIEWED"
  else: ear_status="EAR99_CANDIDATE"
  ear=Finding("ear",ear_status,1.0 if prohibited else .95 if restricted or military_user else .8 if ear_status=="LICENSE_REVIEW" else .45,("EAR jurisdiction/classification/end-use evaluated",),{"eccn":eccn or None,"destination":dest})
  party=self._screen(str(parties.get("end_user",{}).get("name","")))
  if party.status=="MATCH" or prohibited: decision="DENIED"
  elif itar_status=="ITAR_CONTROLLED" or ear_status in {"LICENSE_REQUIRED","LICENSE_REVIEW"}: decision="LICENSE_REQUIRED"
  elif itar_status=="POTENTIALLY_ITAR" or party.status=="POSSIBLE_MATCH" or ear_status=="EAR99_CANDIDATE": decision="MANUAL_REVIEW"
  else: decision="APPROVED"
  return {"jurisdiction":"ITAR" if itar_status!="NOT_INDICATED" else "EAR","classification":explicit_usml or eccn or "UNRESOLVED","license_status":"REQUIRED" if decision=="LICENSE_REQUIRED" else "PROHIBITED" if decision=="DENIED" else "REVIEW" if decision=="MANUAL_REVIEW" else "NLR_CANDIDATE","decision":decision,"confidence":.95 if decision in {"DENIED","APPROVED"} else .65,"requires_human_review":decision!="APPROVED","itar":itar.to_dict(),"ear":ear.to_dict(),"restricted_party":party.to_dict(),"ruleset_version":self.c["ruleset_version"]}
