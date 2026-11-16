"""Additive synthetic ChatMate model adapter 0.5.0."""
from .adapter import ADAPTER_VERSION, Phase5ModelAdapter
from .runtime import ModelPhase5Target, invoke_fresh

__all__ = ["ADAPTER_VERSION", "ModelPhase5Target", "Phase5ModelAdapter", "invoke_fresh"]
