from sqlalchemy.orm import Session

from adapters.database.models.channel_reporting import ChannelReporting
from adapters.database.repositories.channel_reporting_repository import (
    DBChannelReportingRepo,
)


def recompute_channel_reporting(session: Session) -> int:
    """Wipe channel_reporting and recompute from source tables. Return row count.

    Always full-recompute — no date range. The pipeline's date range
    (Step 1) controls which conversions get scored; once scored, the
    reporting table mirrors the full source state.
    """
    DBChannelReportingRepo(session).recompute()
    return session.query(ChannelReporting).count()
