from .base_runner import BaseRunner
from .standard_runner import StandardRunner
from .random_runner import RandomRunner
from .permutation_runner import PermutationRunner
from .file_load_runner import FileLoadRunner

RUNNER_MAP = {
    "auto": StandardRunner,
    "manual": StandardRunner,
    "random": RandomRunner,
    "auto_permutations": PermutationRunner,
    "file_load": FileLoadRunner,
}

__all__ = [
    "BaseRunner",
    "StandardRunner",
    "RandomRunner",
    "PermutationRunner",
    "FileLoadRunner",
    "RUNNER_MAP",
]
