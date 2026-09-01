#!/usr/bin/env python3
"""Run one complete AI inference from a terminal JSON evidence file."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from app.ai.integration import build_ai_pipeline


def main():
 p=argparse.ArgumentParser(); p.add_argument('--evidence',type=Path,required=True); p.add_argument('--config',type=Path,default=Path('configs/application/ai.json')); p.add_argument('--output',type=Path); a=p.parse_args()
 evidence=json.loads(a.evidence.read_text(encoding='utf-8')); config=json.loads(a.config.read_text(encoding='utf-8')); pipeline=build_ai_pipeline(Path.cwd(),config)
 controls=dict(evidence.get('controls',{})); result=pipeline.analyze(evidence,controls); rendered=json.dumps(result,indent=2,sort_keys=True)
 if a.output: a.output.parent.mkdir(parents=True,exist_ok=True); a.output.write_text(rendered+'\n',encoding='utf-8')
 else: print(rendered)
if __name__=='__main__':main()
