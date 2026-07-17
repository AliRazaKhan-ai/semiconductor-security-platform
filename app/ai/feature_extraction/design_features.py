"""Extract bounded design-security features from Yosys and Verilator results."""
from __future__ import annotations
import math
from typing import Any
from app.ai.common import finite_float, clamp

def extract_design(evidence: dict[str,Any]) -> dict[str,float]:
    yosys=dict(evidence.get("yosys",{})); ver=dict(evidence.get("verilator",{}))
    gates=max(0.0, finite_float(yosys.get("gate_count",0),"gate_count")); cells=max(1.0, finite_float(yosys.get("cell_count",gates or 1),"cell_count"))
    return {
      "gate_count_log":math.log1p(gates)/20.0,
      "cell_type_diversity":clamp(finite_float(yosys.get("cell_type_count",0),"cell_type_count")/64.0),
      "unused_logic_ratio":clamp(finite_float(yosys.get("unused_logic_ratio",0),"unused_logic_ratio")),
      "rare_net_ratio":clamp(finite_float(yosys.get("rare_net_count",0),"rare_net_count")/cells),
      "sequential_ratio":clamp(finite_float(yosys.get("sequential_cells",0),"sequential_cells")/cells),
      "combinational_ratio":clamp(finite_float(yosys.get("combinational_cells",0),"combinational_cells")/cells),
      "netlist_delta_ratio":clamp(finite_float(yosys.get("netlist_delta_ratio",0),"netlist_delta_ratio")),
      "simulation_failure_ratio":clamp(finite_float(ver.get("failed_assertions",0),"failed_assertions")/max(1.0,finite_float(ver.get("assertion_count",1),"assertion_count"))) }
