"""Compose the production AI services from validated platform configuration."""
from __future__ import annotations
from pathlib import Path
from typing import Any
from app.ai import AIPipelineService
from app.ai.feature_extraction import FEATURE_NAMES, FeatureExtractionService
from app.ai.feature_extraction.normalization import RobustNormalizer
from app.ai.tensorflow_classifier import TensorFlowClassifierService
from app.ai.pytorch_anomaly import PyTorchAnomalyService
from app.ai.risk_engine import RiskEngineService

def _resolve(root:Path,value:str)->Path:
 p=Path(value); return p if p.is_absolute() else root/p

def build_ai_pipeline(project_root:Path,config:dict[str,Any])->AIPipelineService:
 tfc=dict(config["tensorflow"]); pt=dict(config["pytorch"]); risk=dict(config["risk_engine"])
 normalizer=RobustNormalizer.load(_resolve(project_root,str(config["normalizer_path"])))
 if tuple(normalizer.feature_names)!=FEATURE_NAMES: raise ValueError("normalizer feature schema does not match production schema")
 cnn=TensorFlowClassifierService(_resolve(project_root,str(tfc["model_path"])),tuple(tfc["labels"]),str(tfc.get("version","1.0.0")),tfc.get("sha256"),float(tfc.get("min_confidence",.60)))
 anomaly=PyTorchAnomalyService(_resolve(project_root,str(pt["model_path"])),FEATURE_NAMES,float(pt["threshold"]),float(pt["scale"]),str(pt.get("version","1.0.0")),int(pt.get("latent_dim",8)),pt.get("sha256"))
 risk_service=RiskEngineService(_resolve(project_root,str(risk["model_path"])),FEATURE_NAMES,str(risk.get("version","1.0.0")),risk.get("sha256"))
 return AIPipelineService(FeatureExtractionService(int(config.get("sequence_length",256))),normalizer,cnn,anomaly,risk_service)
