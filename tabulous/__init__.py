"""Tabulous — messy, tabular and fabulous data on demand."""
from .generate import GenerationResult, generate
from .spec import Spec, TabulousError, load_spec
from .truth import Corruption

__all__ = ["generate", "load_spec", "GenerationResult", "Corruption", "Spec", "TabulousError"]
