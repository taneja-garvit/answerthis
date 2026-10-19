"""analysis status and confidence level

Revision ID: b6b77c2062de
Revises: 796f0732d1ff
Create Date: 2026-10-19 16:39:05.762041

- drafts: analysis_status (also the concurrent-analysis lock), timestamps
- claims: processing_error (user-safe failure reason)
- assessments: coarse confidence_level; numeric confidence becomes nullable
- evidence: is_current (superseded passages are kept for assessment history)
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "b6b77c2062de"
down_revision: str | Sequence[str] | None = "796f0732d1ff"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("assessments", sa.Column("confidence_level", sa.String(length=8), nullable=True))
    op.create_check_constraint(
        op.f("ck_assessments_confidence_level"),
        "assessments",
        "confidence_level IN ('LOW', 'MEDIUM', 'HIGH')",
    )
    op.alter_column(
        "assessments", "confidence", existing_type=sa.DOUBLE_PRECISION(precision=53), nullable=True
    )
    op.add_column("claims", sa.Column("processing_error", sa.Text(), nullable=True))
    op.add_column(
        "drafts",
        sa.Column(
            "analysis_status",
            sa.String(length=32),
            server_default=sa.text("'NOT_ANALYZED'"),
            nullable=False,
        ),
    )
    op.create_check_constraint(
        op.f("ck_drafts_analysis_status"),
        "drafts",
        "analysis_status IN ('NOT_ANALYZED', 'ANALYZING', 'ANALYZED', 'FAILED')",
    )
    op.add_column("drafts", sa.Column("analysis_started_at", sa.DateTime(timezone=True)))
    op.add_column("drafts", sa.Column("analyzed_at", sa.DateTime(timezone=True)))
    op.add_column(
        "evidence",
        sa.Column("is_current", sa.Boolean(), server_default=sa.text("true"), nullable=False),
    )
    # Drafts that already have claims (e.g. the seeded demo) count as analyzed.
    op.execute(
        "UPDATE drafts SET analysis_status = 'ANALYZED', analyzed_at = updated_at "
        "WHERE EXISTS (SELECT 1 FROM claims WHERE claims.draft_id = drafts.id)"
    )


def downgrade() -> None:
    op.drop_column("evidence", "is_current")
    op.drop_column("drafts", "analyzed_at")
    op.drop_column("drafts", "analysis_started_at")
    op.drop_constraint(op.f("ck_drafts_analysis_status"), "drafts", type_="check")
    op.drop_column("drafts", "analysis_status")
    op.drop_column("claims", "processing_error")
    # The old schema requires a number; map levels to band midpoints.
    op.execute(
        "UPDATE assessments SET confidence = CASE confidence_level "
        "WHEN 'HIGH' THEN 0.9 WHEN 'MEDIUM' THEN 0.6 ELSE 0.3 END WHERE confidence IS NULL"
    )
    op.alter_column(
        "assessments", "confidence", existing_type=sa.DOUBLE_PRECISION(precision=53), nullable=False
    )
    op.drop_constraint(op.f("ck_assessments_confidence_level"), "assessments", type_="check")
    op.drop_column("assessments", "confidence_level")
