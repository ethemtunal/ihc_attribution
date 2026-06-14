from adapters.database.models.attribution_customer_journey import (
    AttributionCustomerJourney,
)
from adapters.database.repositories.attribution_repository import DBAttributionRepo
from domain.entities.attribution_customer_journey import (
    AttributionCustomerJourneyEntity,
)


def test_insert_many_inserts_new_rows(ihc_db):
    """
    GIVEN no existing rows
    WHEN insert_many is called with two new (conv_id, session_id) entries
    THEN both rows are persisted with the supplied ihc values.
    """
    repo = DBAttributionRepo(ihc_db)
    entries = [
        AttributionCustomerJourneyEntity(conv_id="c1", session_id="s1", ihc=0.3),
        AttributionCustomerJourneyEntity(conv_id="c1", session_id="s2", ihc=0.7),
    ]

    repo.insert_many(entries)

    rows = {
        (r.conv_id, r.session_id): r.ihc
        for r in ihc_db.query(AttributionCustomerJourney).all()
    }
    assert rows == {("c1", "s1"): 0.3, ("c1", "s2"): 0.7}
