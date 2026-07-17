#!/usr/bin/env python3
"""Train and calibrate the Scikit-learn risk classifier."""
from __future__ import annotations
import argparse,json
from pathlib import Path
import joblib,numpy as np
from sklearn.calibration import CalibratedClassifierCV
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import classification_report,roc_auc_score
from sklearn.model_selection import train_test_split
from dataset import load_dataset
def main():
 p=argparse.ArgumentParser(); p.add_argument('--dataset',type=Path,required=True); p.add_argument('--model-signals',type=Path,required=True); p.add_argument('--output',type=Path,required=True); p.add_argument('--seed',type=int,default=42); a=p.parse_args()
 x,_,y=load_dataset(a.dataset); sig=np.load(a.model_signals,allow_pickle=False); signals=np.column_stack([sig['cnn_score'],sig['cnn_confidence'],sig['anomaly_score'],sig['anomaly_confidence']]).astype(np.float32)
 if len(signals)!=len(x): raise ValueError('model signals and dataset length differ')
 z=np.column_stack([x,signals]); xtr,xte,ytr,yte=train_test_split(z,(y>0).astype(int),test_size=.2,stratify=(y>0),random_state=a.seed)
 base=RandomForestClassifier(n_estimators=500,max_depth=14,min_samples_leaf=3,class_weight='balanced_subsample',n_jobs=-1,random_state=a.seed); model=CalibratedClassifierCV(base,method='sigmoid',cv=5); model.fit(xtr,ytr); pred=model.predict(xte); prob=model.predict_proba(xte)[:,1]
 a.output.parent.mkdir(parents=True,exist_ok=True); joblib.dump(model,a.output); a.output.with_suffix('.metrics.json').write_text(json.dumps({"roc_auc":roc_auc_score(yte,prob),"classification_report":classification_report(yte,pred,output_dict=True)},indent=2))
if __name__=='__main__': main()
