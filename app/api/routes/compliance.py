from pathlib import Path

from flask import Blueprint, current_app, g, request, send_file

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
@bp.get("/scans/<scan_id>/report.json")
def rjson(scan_id):return send_file(Path(svc().reporter.json_root)/f"{scan_id}.json",as_attachment=True,mimetype="application/json")
@bp.get("/scans/<scan_id>/report.pdf")
def rpdf(scan_id):return send_file(Path(svc().reporter.pdf_root)/f"{scan_id}.pdf",as_attachment=True,mimetype="application/pdf")
@bp.get("/scans/<scan_id>/government-audit")
def audit(scan_id):return send_file(Path(svc().reporter.audit_root)/f"{scan_id}.json",as_attachment=True,mimetype="application/json")
