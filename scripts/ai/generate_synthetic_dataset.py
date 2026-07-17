#!/usr/bin/env python3
"""Generate a reproducible physics-inspired dataset for integration tests and initial training."""
from __future__ import annotations
import argparse
from pathlib import Path
import numpy as np
def main():
 p=argparse.ArgumentParser(); p.add_argument('--output',type=Path,required=True); p.add_argument('--samples',type=int,default=5000); p.add_argument('--seed',type=int,default=42); a=p.parse_args(); rng=np.random.default_rng(a.seed)
 labels=rng.choice(3,size=a.samples,p=[.55,.25,.20]); features=rng.normal(0,1,(a.samples,32)).astype(np.float32); seq=rng.normal(0,1,(a.samples,256,3)).astype(np.float32)
 for i,label in enumerate(labels):
  if label==1: seq[i,:,0]+=0.8*np.sin(np.linspace(0,24*np.pi,256)); features[i,[2,3,18,19,22]]+=2.0
  elif label==2: seq[i,80:120,1]+=2.5; features[i,[24,25,26,28,29]]+=2.2
 a.output.parent.mkdir(parents=True,exist_ok=True); np.savez_compressed(a.output,features=features,sequences=seq,labels=labels)
if __name__=='__main__': main()
