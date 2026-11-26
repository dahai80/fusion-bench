"""FusionOffice-Bench (issue #56).

Office-domain eval testset for the fusion-trainer flywheel: 32 tasks across
office_xlsx / office_docx / office_pptx (apps x steps difficulty axis),
deterministic structural validators vendored from fusion-trainer#90, and a
runner emitting a fusion-eval-compatible summary.json.
"""

from .runner import run_office
from .tasks import OFFICE_TASKS, OfficeTask
from .validators import validate

__all__ = [
    "OFFICE_TASKS",
    "OfficeTask",
    "validate",
    "run_office",
]
