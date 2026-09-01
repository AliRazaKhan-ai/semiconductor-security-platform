from __future__ import annotations

from flask import Blueprint, current_app, jsonify

bp=Blueprint('hardware_status',__name__,url_prefix='/hardware')
@bp.get('/status')
def status():
    pipeline=current_app.extensions.get('semisecure.hardware_pipeline')
    return jsonify({'status':'READY' if pipeline else 'UNAVAILABLE','components':['opentitan','chipwhisperer','yosys','verilator','sbom','digital_twin'],'write_controls':False,'terminal_controlled':True}),200 if pipeline else 503
