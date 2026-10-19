from enum import StrEnum


class ProjectStatus(StrEnum):
    ACTIVE = "ACTIVE"
    ARCHIVED = "ARCHIVED"


class SourceAccessStatus(StrEnum):
    AVAILABLE = "AVAILABLE"  # full text ingested
    ABSTRACT_ONLY = "ABSTRACT_ONLY"
    UNAVAILABLE = "UNAVAILABLE"


class DraftAnalysisStatus(StrEnum):
    NOT_ANALYZED = "NOT_ANALYZED"
    ANALYZING = "ANALYZING"  # also acts as a lock against concurrent analyze runs
    ANALYZED = "ANALYZED"
    FAILED = "FAILED"


class ConfidenceLevel(StrEnum):
    """Coarse confidence in the claim-vs-evidence *classification*; never a
    probability that the scientific claim is true."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class ClaimStatus(StrEnum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    READY = "READY"
    ERROR = "ERROR"


class AccessLevel(StrEnum):
    FULL_TEXT = "FULL_TEXT"
    ABSTRACT = "ABSTRACT"
    USER_PROVIDED = "USER_PROVIDED"


class Verdict(StrEnum):
    SUPPORTED = "SUPPORTED"
    PARTIALLY_SUPPORTED = "PARTIALLY_SUPPORTED"
    UNSUPPORTED = "UNSUPPORTED"
    UNVERIFIABLE = "UNVERIFIABLE"


class IssueType(StrEnum):
    FIGURE_MISMATCH = "FIGURE_MISMATCH"
    POPULATION_MISMATCH = "POPULATION_MISMATCH"
    OUTCOME_MISMATCH = "OUTCOME_MISMATCH"
    OVERGENERALIZATION = "OVERGENERALIZATION"
    CAUSAL_OVERSTATEMENT = "CAUSAL_OVERSTATEMENT"
    WORDING_STRENGTH = "WORDING_STRENGTH"
    SOURCE_MISMATCH = "SOURCE_MISMATCH"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    EVIDENCE_UNAVAILABLE = "EVIDENCE_UNAVAILABLE"
    OTHER = "OTHER"


class ReviewDecision(StrEnum):
    KEEP = "KEEP"
    QUALIFY = "QUALIFY"
    REPLACE = "REPLACE"
    REMOVE = "REMOVE"


class ReviewStatus(StrEnum):
    """Derived, never stored: a claim is reviewed only once a human decides."""

    NEEDS_REVIEW = "NEEDS_REVIEW"
    REVIEWED = "REVIEWED"


class EvidenceAvailability(StrEnum):
    """Derived from evidence rows and source access status, for honest display."""

    FULL_TEXT = "FULL_TEXT"
    ABSTRACT = "ABSTRACT"
    USER_PROVIDED = "USER_PROVIDED"
    UNAVAILABLE = "UNAVAILABLE"
