from datetime import UTC,datetime
from pathlib import Path
import json
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer,Table
from app.compliance.common import canonical_hash,sign
class ComplianceReportGenerator:
 def __init__(self,root:Path,c:dict):
  self.root=root;self.c=c;self.json_root=root/"reports/json";self.pdf_root=root/"reports/pdf";self.audit_root=root/"government_audit"
  [p.mkdir(parents=True,exist_ok=True) for p in (self.json_root,self.pdf_root,self.audit_root)]
 def generate(self,scan_id:str,chip_id:str,decision:dict,evidence_hashes:dict,event_chain_head:str)->dict:
  r={"schema_version":"1.0","report_type":"SEMICONDUCTOR_EXPORT_COMPLIANCE","scan_id":scan_id,"chip_id":chip_id,"generated_at_utc":datetime.now(UTC).isoformat(),"regulatory_notice":self.c["regulatory_notice"],"decision":decision,"evidence_hashes":evidence_hashes,"event_chain_head":event_chain_head};rh=canonical_hash(r);r["report_hash"]=rh;r["signature"]=sign(r)
  jp=self.json_root/f"{scan_id}.json";jp.write_text(json.dumps(r,indent=2)+"\n")
  pp=self.pdf_root/f"{scan_id}.pdf"; styles=getSampleStyleSheet(); doc=SimpleDocTemplate(str(pp),pagesize=A4,title=f"Compliance {scan_id}"); rows=[["Scan ID",scan_id],["Chip ID",chip_id],["Decision",decision["decision"]],["Status",decision["status"]],["Risk",f'{decision["risk_score"]:.4f}'],["Confidence",f'{decision["confidence"]:.4f}'],["Report Hash",rh]]; doc.build([Paragraph("SemiSecure Government Compliance Report",styles["Title"]),Spacer(1,12),Paragraph(self.c["regulatory_notice"],styles["BodyText"]),Spacer(1,12),Table(rows)])
  a={"schema_version":"1.0","package_type":"GOVERNMENT_AUDIT_PACKAGE","scan_id":scan_id,"chip_id":chip_id,"generated_at_utc":datetime.now(UTC).isoformat(),"report_hash":rh,"event_chain_head":event_chain_head,"evidence_hashes":evidence_hashes,"decision_summary":{"decision":decision["decision"],"status":decision["status"],"risk_score":decision["risk_score"],"confidence":decision["confidence"]}};a["audit_hash"]=canonical_hash(a);a["signature"]=sign(a);ap=self.audit_root/f"{scan_id}.json";ap.write_text(json.dumps(a,indent=2)+"\n")
  return {"report_hash":rh,"government_audit_hash":a["audit_hash"],"json_path":str(jp),"pdf_path":str(pp),"audit_path":str(ap),"signature":r["signature"]}
