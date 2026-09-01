from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from app.hardware.chipwhisperer import ChipWhispererAdapter
from app.hardware.common import HardwareIntegrationError
from app.hardware.digital_twin import DigitalTwinService
from app.hardware.opentitan import OpenTitanAdapter
from app.hardware.sbom import SBOMGenerator, validate_sbom
from app.hardware.verilator import VerilatorAdapter
from app.hardware.yosys import YosysAdapter
from app.storage.event_store import EventStore

logger=logging.getLogger(__name__)
@dataclass(frozen=True,slots=True)
class HardwarePipelineResult:
    passed:bool; status:str; results:dict[str,Any]; failed_stage:str|None=None

class HardwareSecurityPipeline:
    STAGES=('opentitan','chipwhisperer','yosys','verilator','sbom','digital_twin')
    def __init__(self,*,root:Path,event_store:EventStore,publisher:Any|None=None)->None:
        self.root=root; self.events=event_store; self.publisher=publisher
        self.opentitan=OpenTitanAdapter.from_project(root); self.chipwhisperer=ChipWhispererAdapter.from_project(root)
        self.yosys=YosysAdapter.from_project(root); self.verilator=VerilatorAdapter(); self.twins=DigitalTwinService.from_project(root); self.sbom=SBOMGenerator()
    def _record(self,scan_id,chip_id,correlation_id,event_type,stage,payload):
        record=self.events.append(scan_id=scan_id,chip_id=chip_id,event_type=event_type,pipeline_stage=stage,correlation_id=correlation_id,source_component=f'hardware.{stage}',component_version='1.0.0',payload=payload,evidence_hashes={k:v for k,v in payload.items() if k.endswith('_digest') and isinstance(v,str)})
        if self.publisher:self.publisher.publish_record(record)
    def _yosys_stage(self, manifest: dict[str, Any]) -> dict[str, Any]:
        """Synthesise the candidate RTL, differencing against a reference when one is declared.

        The structural delta is reported as evidence, not as a gate. A legitimate design
        revision also diverges from its predecessor, so divergence is weighted by the model
        and surfaced to a reviewer rather than triggering automatic rejection. The stage's
        pass/fail remains governed by the absolute policy checks in rules.evaluate().
        """
        rtl = Path(manifest["rtl_file"])
        top = str(manifest["top_module"])
        reference = manifest.get("reference_rtl_file")

        if not reference:
            payload = self.yosys.analyse(rtl, top).to_dict()
            payload["structural_analysis"] = {
                "available": False,
                "reason": "NO_REFERENCE_RTL_IN_MANIFEST",
                "netlist_delta_ratio": None,
            }
            return payload

        result, report = self.yosys.analyse_against_reference(
            rtl, Path(reference), top
        )

        reference_cells = int(report["reference_metrics"]["cells"])
        candidate_cells = int(report["candidate_metrics"]["cells"])
        denominator = max(1, reference_cells, candidate_cells)
        bounded_ratio = min(
            1.0,
            float(report["delta"]["absolute_cell_delta"]) / float(denominator),
        )

        report["netlist_delta_ratio_reference_normalised"] = report["netlist_delta_ratio"]
        report["netlist_delta_ratio"] = bounded_ratio
        report["normalisation"] = "max(reference_cells, candidate_cells)"
        report["available"] = True

        payload = result.to_dict()
        payload["structural_analysis"] = report
        payload["netlist_delta_ratio"] = bounded_ratio
        payload["structural_reasons"] = report["structural_reasons"]
        return payload

    def run(self,*,scan_id:str,chip_id:str,correlation_id:str,manifest:dict[str,Any])->HardwarePipelineResult:
        results={}
        handlers={
          'opentitan':lambda:self.opentitan.verify_file(Path(manifest['opentitan_evidence'])).to_dict(),
          'chipwhisperer':lambda:self.chipwhisperer.analyse_files(Path(manifest['side_channel_trace']),Path(manifest['side_channel_reference'])).to_dict(),
          'yosys':lambda:self._yosys_stage(manifest),
          'verilator':lambda:self.verilator.simulate(Path(manifest['rtl_file']),Path(manifest['testbench_file']),str(manifest['top_module'])).to_dict(),
          'sbom':lambda:self.sbom.generate(chip_id=chip_id,artifacts=[Path(p) for p in manifest['sbom_artifacts']],output=self.root/'data/sbom'/f'{scan_id}.cdx.json',metadata=manifest.get('sbom_metadata')).to_dict(),
        }
        for stage in ('opentitan','chipwhisperer','yosys','verilator','sbom'):
            self._record(scan_id,chip_id,correlation_id,'stage.started',stage,{'status':'STARTED'})
            try: result=handlers[stage]()
            except Exception as exc:
                payload={'status':'FAILED','error_type':type(exc).__name__,'message':str(exc)}; self._record(scan_id,chip_id,correlation_id,'stage.failed',stage,payload)
                return HardwarePipelineResult(False,'QUARANTINED',results,stage)
            results[stage]=result
            if not result.get('passed',False):
                self._record(scan_id,chip_id,correlation_id,'stage.failed',stage,result); return HardwarePipelineResult(False,'QUARANTINED',results,stage)
            self._record(scan_id,chip_id,correlation_id,'stage.completed',stage,result)
        evidence={'chip_id':chip_id,'puf_identity_hash':str(manifest['puf_identity_hash']),'rtl_digest':results['yosys']['rtl_digest'],'netlist_digest':results['yosys']['netlist_digest'],'firmware_digest':results['opentitan']['firmware_digest'],'sbom_digest':results['sbom']['document_digest']}
        stage='digital_twin'; self._record(scan_id,chip_id,correlation_id,'stage.started',stage,{'status':'STARTED'})
        try: result=self.twins.verify(str(manifest['twin_id']),evidence).to_dict()
        except Exception as exc:
            self._record(scan_id,chip_id,correlation_id,'stage.failed',stage,{'status':'FAILED','message':str(exc)}); return HardwarePipelineResult(False,'QUARANTINED',results,stage)
        results[stage]=result
        if not result['passed']:
            self._record(scan_id,chip_id,correlation_id,'stage.failed',stage,result); return HardwarePipelineResult(False,'QUARANTINED',results,stage)
        self._record(scan_id,chip_id,correlation_id,'stage.completed',stage,result)
        return HardwarePipelineResult(True,'HARDWARE_VALIDATED',results)
