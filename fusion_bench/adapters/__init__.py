"""Model adapters for lm-evaluation-harness compatibility.

All model inference goes through fusion-mlx HTTP API.
Never imports MLX, torch, or transformers directly.
"""

from .mlx_model import MLXModel

__all__ = ["MLXModel"]