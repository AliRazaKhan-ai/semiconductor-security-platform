from __future__ import annotations
import re
def parse_output(build_log:str,output:str)->tuple[tuple[str,...],int,int,tuple[str,...]]:
    reasons=[]; warnings=tuple(line.strip() for line in build_log.splitlines() if '%Warning' in line)
    if any(token in output.upper() for token in ('ASSERTION FAILED','%ERROR','$FATAL','TEST FAILED')): reasons.append('SIMULATION_ASSERTION_FAILURE')
    assertions=sum(1 for line in output.splitlines() if 'ASSERT' in line.upper())
    matches=re.findall(r'(?:CYCLES|cycle_count)\s*[:=]\s*(\d+)',output,re.I); cycles=int(matches[-1]) if matches else 0
    if 'SEMISURE_PASS' not in output: reasons.append('PASS_MARKER_MISSING')
    return tuple(reasons),assertions,cycles,warnings
