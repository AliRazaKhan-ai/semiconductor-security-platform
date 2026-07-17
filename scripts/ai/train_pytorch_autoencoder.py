#!/usr/bin/env python3
"""Train an autoencoder only on clean feature vectors and derive an anomaly threshold."""
from __future__ import annotations
import argparse,json,random,sys
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from dataset import load_dataset
from app.ai.pytorch_anomaly.loader import build_autoencoder
def main():
 p=argparse.ArgumentParser(); p.add_argument('--dataset',type=Path,required=True); p.add_argument('--output',type=Path,required=True); p.add_argument('--epochs',type=int,default=100); p.add_argument('--batch-size',type=int,default=128); p.add_argument('--seed',type=int,default=42); a=p.parse_args()
 import torch
 random.seed(a.seed); np.random.seed(a.seed); torch.manual_seed(a.seed)
 x,_,y=load_dataset(a.dataset); clean=x[y==0]
 if len(clean)<20: raise ValueError('at least 20 clean samples are required')
 tensor=torch.tensor(clean,dtype=torch.float32); loader=torch.utils.data.DataLoader(tensor,batch_size=a.batch_size,shuffle=True)
 model=build_autoencoder(x.shape[1],max(4,x.shape[1]//4)); opt=torch.optim.AdamW(model.parameters(),lr=1e-3,weight_decay=1e-5); loss_fn=torch.nn.MSELoss()
 model.train()
 for _ in range(a.epochs):
  for batch in loader: opt.zero_grad(); loss=loss_fn(model(batch),batch); loss.backward(); torch.nn.utils.clip_grad_norm_(model.parameters(),1.0); opt.step()
 model.eval()
 with torch.inference_mode(): errors=((model(tensor)-tensor)**2).mean(dim=1).numpy()
 threshold=float(np.quantile(errors,.995)); scale=float(max(np.std(errors),1e-8)); a.output.parent.mkdir(parents=True,exist_ok=True); torch.save({"state_dict":model.state_dict(),"input_dim":x.shape[1],"threshold":threshold,"scale":scale},a.output); a.output.with_suffix('.metrics.json').write_text(json.dumps({"threshold":threshold,"scale":scale,"clean_samples":len(clean)},indent=2))
if __name__=='__main__': main()
