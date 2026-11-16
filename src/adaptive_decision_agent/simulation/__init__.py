"""Deterministic inventory simulation with externally supplied orders."""

from .engine import PolicyObservation, SimulationResult, simulate

__all__ = ["PolicyObservation", "SimulationResult", "simulate"]
