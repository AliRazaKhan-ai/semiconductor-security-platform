from __future__ import annotations
from pathlib import Path
import json
from app.compliance.common import canonical_hash
from app.compliance.export_control import ExportControlEngine
from app.compliance.supplier_risk import SupplierRiskEngine
from app.compliance.policy_engine import PolicyEngine
from app.compliance.reporting import ComplianceReportGenerator
class ComplianceService:
 def __init__(self,root:Path,config:dict,event_store,publisher=None,blockchain_service=None):
  self.root=root;self.c=config;self.events=event_store;self.publisher=publisher;self.blockchain=blockchain_service;self.export=ExportControlEngine(config,root);self.supplier=SupplierRiskEngine(config["supplier_risk"]);self.policy=PolicyEngine(config["policy"]);self.reporter=ComplianceReportGenerator(root/config["reporting"]["root"],config["reporting"])
 def _add(self,scan,chip,etype,stage,corr,payload,hashes=None):
  r=self.events.append(scan_id=scan,chip_id=chip,event_type=etype,pipeline_stage=stage,correlation_id=corr,source_component="compliance-engine",component_version="2.0.0",payload=payload,evidence_hashes=hashes or {})
  if self.publisher:self.publisher.publish_record(r)
  return r
 def evaluate(self,p:dict,corr:str)->dict:
  scan=str(p["scan_id"]);snap=self.events.snapshot(scan);chip=str(snap["chip_id"]);ai=dict(p.get("ai",snap.get("ai") or {}));e=self.export.evaluate(dict(p.get("item",{})),dict(p.get("transaction",{})),dict(p.get("parties",{})));s=self.supplier.evaluate(dict(p.get("supplier",{})),ai);d=self.policy.decide(e,s,ai)
  self._add(scan,chip,"supplier_risk.completed","SUPPLIER_RISK",corr,{"status":"PASSED","supplier_risk":s})
  self._add(scan,chip,"export_control.completed","EXPORT_CONTROL",corr,{"status":e["decision"],"export_control":e})
  ce=self._add(scan,chip,"compliance.completed","COMPLIANCE",corr,{"status":d["status"],"decision":d["decision"],"score":d["confidence"],"compliance":d,"itar_status":e["itar"]["status"],"ear_status":e["ear"]["status"],"supplier_risk":s["risk_score"]},{"export_control":canonical_hash(e),"supplier_risk":canonical_hash(s),"ai":canonical_hash(ai)})
  rep=self.reporter.generate(scan,chip,d,ce.evidence_hashes,ce.event_hash)
  self._add(scan,chip,"compliance.report_generated","COMPLIANCE_REPORT",corr,{"status":"GENERATED",**rep},{"compliance_report":rep["report_hash"]})
  self._add(scan,chip,"government_audit.generated","GOVERNMENT_AUDIT",corr,{"status":"GENERATED",**rep},{"government_audit":rep["government_audit_hash"]})
  bc=None
  bc_error=None
  if p.get("anchor_to_blockchain",True):
   if self.blockchain is None:
    bc_error={
     "code":"blockchain_service_unavailable",
     "message":"Blockchain service is unavailable"
    }
   else:
    try:
     bc=self.blockchain.record_scan(scan,corr)
    except Exception as exc:
     bc_error={
      "code":"blockchain_anchor_failed",
      "error_type":type(exc).__name__,
      "message":str(exc)
     }
  out={
   "scan_id":scan,
   "chip_id":chip,
   "decision":d,
   "export_control":e,
   "supplier_risk":s,
   "report":rep,
   "blockchain":bc,
   "blockchain_error":bc_error
  }
  dp=self.root/self.c["decision_root"]/f"{scan}.json"
  dp.parent.mkdir(parents=True,exist_ok=True)
  dp.write_text(json.dumps(out,indent=2)+"\n",encoding="utf-8")
  return out
 def status(self):return {"enabled":True,"ruleset_version":self.c["ruleset_version"],"mode":"decision_support_fail_closed","legal_authority":False}
 def read(self,scan):
  path=self.root/self.c["decision_root"]/f"{scan}.json"
  if not path.exists():
   raise FileNotFoundError(f"Compliance decision not found for scan {scan}")
  return json.loads(path.read_text(encoding="utf-8"))
