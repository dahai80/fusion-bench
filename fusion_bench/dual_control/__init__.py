"""Dual-control agent eval (issue #51, tau2-bench method).

Agent + simulated user acting on a shared deterministic world; compositional
task generator with verifiable end-state checks. Design doc:
docs/design-dual-control-51.md
"""

from .generator import DualTask, check_end_state, generate_task
from .runner import parse_action, run_episode, run_suite, user_message
from .user_sim import LLMUser, ScriptedUser, SimulatedUser, UserTurn
from .world import World, build_initial_state, world_from_state

__all__ = [
    "DualTask",
    "Requirement",
    "generate_task",
    "check_end_state",
    "World",
    "build_initial_state",
    "world_from_state",
    "SimulatedUser",
    "UserTurn",
    "ScriptedUser",
    "LLMUser",
    "run_episode",
    "run_suite",
    "parse_action",
    "user_message",
]
