"""Pure report transformations; no I/O and no access to an orchestrator."""

from .delete_sentence import delete_sentence
from .reselect_claims import reselect_claims
from .rewrite_sentence import rewrite_sentence

__all__ = ["delete_sentence", "rewrite_sentence", "reselect_claims"]
