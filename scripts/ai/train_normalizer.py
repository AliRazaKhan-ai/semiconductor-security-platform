#!/usr/bin/env python3
"""Fit and persist the production robust normalizer using training features only."""
from __future__ import annotations
import argparse,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from dataset import load_dataset
from app.ai.feature_extraction.schemas import FEATURE_NAMES
from app.ai.feature_extraction.normalization import RobustNormalizer
def main():
 p=argparse.ArgumentParser(); p.add_argument('--dataset',type=Path,required=True); p.add_argument('--output',type=Path,required=True); a=p.parse_args(); x,_,_=load_dataset(a.dataset)
 RobustNormalizer.fit(x,FEATURE_NAMES).save(a.output)
if __name__=='__main__':main()
