from __future__ import annotations

import cmath
import hashlib
import math
from statistics import mean

from app.hardware.chipwhisperer.preprocessing import align, centre_scale, validate_trace
from app.hardware.chipwhisperer.schemas import ChipWhispererResult, TraceStatistics
from app.hardware.common import canonical_json


def _spectrum(values:list[float])->list[float]:
    n=len(values); bins=min(n//2,256); return [abs(sum(v*cmath.exp(-2j*math.pi*k*i/n) for i,v in enumerate(values))) for k in range(bins)]
def analyse_trace(candidate:list[float], reference:list[float], *, anomaly_threshold:float=0.35)->ChipWhispererResult:
    candidate=validate_trace(candidate); reference=validate_trace(reference); aligned,shift,corr=align(reference,candidate)
    normalized=centre_scale(aligned); mu=mean(candidate); variance=sum((v-mu)**2 for v in candidate)/len(candidate); sd=variance**0.5
    rms=(sum(v*v for v in candidate)/len(candidate))**0.5; p2p=max(candidate)-min(candidate); crest=max(abs(v) for v in candidate)/max(rms,1e-12)
    spectrum=_spectrum(normalized); total=sum(spectrum) or 1.0; centroid=sum(i*p for i,p in enumerate(spectrum))/total/max(len(spectrum)-1,1)
    high=sum(spectrum[len(spectrum)//2:])/total
    distribution=min(1.0,abs(sd-1.0)/3.0); anomaly=max(0.0,min(1.0,0.55*(1-corr)+0.25*high+0.20*distribution))
    reasons=[]
    if corr<0.70: reasons.append('LOW_REFERENCE_CORRELATION')
    if anomaly>anomaly_threshold: reasons.append('SIDE_CHANNEL_ANOMALY')
    stats=TraceStatistics(len(candidate),mu,sd,rms,p2p,crest,centroid,high,corr)
    digest=hashlib.sha256(canonical_json({'trace':candidate,'shift':shift})).hexdigest()
    return ChipWhispererResult(not reasons,'CLEAN' if not reasons else 'ANOMALOUS',anomaly,anomaly_threshold,tuple(reasons),stats,digest)
