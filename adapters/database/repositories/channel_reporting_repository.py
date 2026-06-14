from sqlalchemy import text

from adapters.database.repositories.base_repository import BaseRepo
from domain.entities.channel_reporting_export_row import ChannelReportingExportRow

_DELETE_SQL = "DELETE FROM channel_reporting"

_INSERT_SQL = """
INSERT INTO channel_reporting (channel_name, date, cost, ihc, ihc_revenue)
WITH cost_per_pair AS (
    SELECT
        ss.channel_name,
        ss.event_date AS date,
        SUM(COALESCE(sc.cost, 0)) AS cost
    FROM session_sources ss
    LEFT JOIN session_costs sc ON sc.session_id = ss.session_id
    GROUP BY ss.channel_name, ss.event_date
),
ihc_per_pair AS (
    SELECT
        ss.channel_name,
        ss.event_date AS date,
        SUM(acj.ihc) AS ihc,
        SUM(acj.ihc * c.revenue) AS ihc_revenue
    FROM attribution_customer_journey acj
    JOIN session_sources ss ON ss.session_id = acj.session_id
    JOIN conversions c       ON c.conv_id   = acj.conv_id
    GROUP BY ss.channel_name, ss.event_date
)
SELECT
    cp.channel_name,
    cp.date,
    cp.cost,
    COALESCE(ip.ihc, 0)         AS ihc,
    COALESCE(ip.ihc_revenue, 0) AS ihc_revenue
FROM cost_per_pair cp
LEFT JOIN ihc_per_pair ip
       ON ip.channel_name = cp.channel_name
      AND ip.date         = cp.date
"""

_EXPORT_SQL = """
SELECT
    channel_name,
    date,
    cost,
    ihc,
    ihc_revenue,
    CASE WHEN ihc  != 0 THEN cost        / ihc  ELSE NULL END AS cpo,
    CASE WHEN cost != 0 THEN ihc_revenue / cost ELSE NULL END AS roas
FROM channel_reporting
WHERE (:start IS NULL OR date >= :start)
  AND (:end   IS NULL OR date <= :end)
ORDER BY date, channel_name
"""


class DBChannelReportingRepo(BaseRepo):
    def recompute(self) -> None:
        """Wipe channel_reporting and rebuild from source tables in two SQL passes.

        Idempotent by construction: DELETE everything, INSERT a fresh aggregation.
        Includes (channel, date) rows for sessions with no attribution
        (cost > 0, ihc = 0). Cost is summed per unique session via a separate
        CTE so sessions attributed to multiple conversions are NOT
        double-counted.
        """
        self.session.execute(text(_DELETE_SQL))
        self.session.execute(text(_INSERT_SQL))
        self.session.commit()

    def get_for_export(
        self,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> list[ChannelReportingExportRow]:
        """Read channel_reporting with CPO + ROAS computed in SQL.

        CPO = cost / ihc, NULL when ihc = 0.
        ROAS = ihc_revenue / cost, NULL when cost = 0.
        Optionally filtered by inclusive date range.
        """
        rows = self.session.execute(
            text(_EXPORT_SQL),
            {"start": start_date, "end": end_date},
        ).all()
        return [ChannelReportingExportRow.model_validate(r._mapping) for r in rows]
