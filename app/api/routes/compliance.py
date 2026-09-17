from pathlib import Path

from flask import Blueprint, current_app, g, request, send_file
from werkzeug.exceptions import NotFound

from app.api.response import success

bp=Blueprint("compliance_api",__name__,url_prefix="/api/v1/compliance")
def svc():
 s=current_app.extensions.get("semisecure.compliance_service")
 if s is None:raise RuntimeError("Compliance service unavailable")
 return s
@bp.get("/status")
def status():return success(svc().status())
@bp.post("/evaluate")
def evaluate():return success(svc().evaluate(request.get_json(),g.correlation_id),status=201)
@bp.get("/scans/<scan_id>")
def decision(scan_id):return success(svc().read(scan_id))
def artifact(root,scan_id,suffix,mimetype):
 """Send a compliance artifact, or 404 when the scan produced none.

 send_file raises FileNotFoundError on a missing path, which the error handler
 reports as 500. A scan that stopped before COMPLIANCE has no report, and that is
 an absent resource rather than a server fault.
 """
 p=Path(root)/f"{scan_id}{suffix}"
 if not p.is_file():raise NotFound(f"No compliance artifact for scan {scan_id}")
 return send_file(p,as_attachment=True,mimetype=mimetype)
@bp.get("/scans/<scan_id>/report.json")
def rjson(scan_id):return artifact(svc().reporter.json_root,scan_id,".json","application/json")
@bp.get("/scans/<scan_id>/report.pdf")
def rpdf(scan_id):return artifact(svc().reporter.pdf_root,scan_id,".pdf","application/pdf")
@bp.get("/scans/<scan_id>/government-audit")
def audit(scan_id):return artifact(svc().reporter.audit_root,scan_id,".json","application/json")
