from __future__ import annotations
import math
from statistics import mean

def validate_trace(values:list[float], minimum_samples:int=128)->list[float]:
    if len(values)<minimum_samples: raise ValueError(f'trace requires at least {minimum_samples} samples')
    if any(not math.isfinite(v) for v in values): raise ValueError('trace contains non-finite values')
    return values

def centre_scale(values:list[float])->list[float]:
    mu=mean(values); variance=sum((v-mu)**2 for v in values)/len(values); sigma=max(variance**0.5,1e-12)
    return [(v-mu)/sigma for v in values]

def align(reference:list[float], candidate:list[float], maximum_shift:int=32)->tuple[list[float],int,float]:
    n=min(len(reference),len(candidate)); r=centre_scale(reference[:n]); c=centre_scale(candidate[:n]); best=(-2.0,0,c)
    for shift in range(-maximum_shift,maximum_shift+1):
        if shift>=0: a=r[shift:]; b=c[:n-shift]
        else: a=r[:n+shift]; b=c[-shift:]
        if len(a)<32: continue
        corr=sum(x*y for x,y in zip(a,b))/len(a)
        if corr>best[0]: best=(corr,shift,c)
    corr,shift,_=best
    aligned=c[shift:]+[0.0]*shift if shift>=0 else [0.0]*(-shift)+c[:n+shift]
    return aligned[:n],shift,corr
