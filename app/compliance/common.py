from __future__ import annotations
from dataclasses import asdict,dataclass,field
from hashlib import sha256
import hmac,json,math,os
from typing import Any
class ComplianceError(RuntimeError): pass
def canonical_json(v:Any)->str:return json.dumps(v,sort_keys=True,separators=(",",":"),ensure_ascii=False)
def canonical_hash(v:Any)->str:return sha256(canonical_json(v).encode()).hexdigest()
def clamp(v:Any)->float:
 n=float(v)
 if not math.isfinite(n): raise ValueError("non-finite value")
 return max(0.0,min(1.0,n))
def sign(v:Any)->str:
 key=os.getenv("SEMISURE_COMPLIANCE_SIGNING_KEY","development-only-change-me").encode()
 return hmac.new(key,canonical_json(v).encode(),sha256).hexdigest()
@dataclass(frozen=True,slots=True)
class Finding:
 control:str;status:str;score:float;reasons:tuple[str,...]=();details:dict[str,Any]=field(default_factory=dict)
 def to_dict(self):return asdict(self)
