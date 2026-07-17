"""PyTorch autoencoder architecture and integrity-checked state loading."""
from __future__ import annotations
from hashlib import sha256
from pathlib import Path
from app.ai.common import AIModelError

def build_autoencoder(input_dim:int,latent_dim:int=8):
    try: import torch.nn as nn
    except ImportError as exc: raise AIModelError("PyTorch is not installed") from exc
    class Autoencoder(nn.Module):
        def __init__(self):
            super().__init__(); hidden=max(16,input_dim//2)
            self.encoder=nn.Sequential(nn.Linear(input_dim,hidden),nn.LayerNorm(hidden),nn.GELU(),nn.Linear(hidden,latent_dim))
            self.decoder=nn.Sequential(nn.Linear(latent_dim,hidden),nn.GELU(),nn.Linear(hidden,input_dim))
        def forward(self,x): return self.decoder(self.encoder(x))
    return Autoencoder()
def _hash(path:Path)->str:
    h=sha256();
    with path.open('rb') as f:
        for c in iter(lambda:f.read(1048576),b''): h.update(c)
    return h.hexdigest()
def load_autoencoder(path:Path,input_dim:int,latent_dim:int=8,expected_hash:str|None=None):
    if not path.is_file(): raise AIModelError(f"PyTorch model not found: {path}")
    if expected_hash and _hash(path)!=expected_hash: raise AIModelError("PyTorch model integrity verification failed")
    try: import torch
    except ImportError as exc: raise AIModelError("PyTorch is not installed") from exc
    model=build_autoencoder(input_dim,latent_dim); payload=torch.load(path,map_location='cpu',weights_only=True); model.load_state_dict(payload["state_dict"] if "state_dict" in payload else payload); model.eval(); return model
