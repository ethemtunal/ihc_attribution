from unittest.mock import MagicMock, patch

import pytest

from adapters.ihc.client import (
    IhcApiError,
    IhcClient,
    IhcComputeResponse,
)
from domain.entities.customer_journey import CustomerJourneyEntity
from domain.entities.journey_touchpoint import JourneyTouchpointEntity


def _journey(
    conv_id: str = "c1", sessions: list[JourneyTouchpointEntity] | None = None
) -> CustomerJourneyEntity:
    if sessions is None:
        sessions = [
            JourneyTouchpointEntity(
                session_id="s1",
                timestamp="2024-01-05T09:00:00",
                channel="SEA",
                holder_engagement=1,
                closer_engagement=0,
                impression_interaction=0,
            ),
            JourneyTouchpointEntity(
                session_id="s2",
                timestamp="2024-01-08T18:30:00",
                channel="Direct",
                holder_engagement=0,
                closer_engagement=1,
                impression_interaction=0,
            ),
        ]
    return CustomerJourneyEntity(
        conversion_id=conv_id,
        conv_date="2024-01-10",
        conv_time="12:00:00",
        revenue=100.0,
        user_id="u1",
        sessions=sessions,
    )


def _ok_response(value: list[dict] | None = None) -> MagicMock:
    return MagicMock(
        status_code=200,
        json=lambda: {
            "statusCode": 200,
            "value": value or [],
            "partialFailureErrors": [],
        },
    )


@patch("adapters.ihc.client.requests.post")
def test_compute_posts_to_compute_ihc_with_correct_headers_and_query_param(
    mock_post,
):
    """
    GIVEN a configured client
    WHEN compute is called
    THEN it POSTs to /v1/compute_ihc with the x-api-key header and conv_type_id
         in the query string (matching the IHC docs).
    """
    mock_post.return_value = _ok_response()
    client = IhcClient(api_key="KEY", conv_type_id="TYPE")

    client.compute([_journey()])

    assert mock_post.called
    call = mock_post.call_args
    assert call.args[0] == "https://api.ihc-attribution.com/v1/compute_ihc"
    assert call.kwargs["params"] == {"conv_type_id": "TYPE"}
    assert call.kwargs["headers"]["x-api-key"] == "KEY"
    assert call.kwargs["headers"]["Content-Type"] == "application/json"


@patch("adapters.ihc.client.requests.post")
def test_compute_flattens_journeys_to_session_list_under_customer_journeys_key(
    mock_post,
):
    """
    GIVEN two journeys with 2 and 3 touchpoints
    WHEN compute is called
    THEN the request body has customer_journeys as a flat list of 5 sessions,
         each tagged with its parent conversion_id.
    """
    mock_post.return_value = _ok_response()
    client = IhcClient(api_key="KEY", conv_type_id="TYPE")
    j1 = _journey(conv_id="c1")
    j2 = _journey(
        conv_id="c2",
        sessions=[
            JourneyTouchpointEntity(
                session_id=f"s2_{i}",
                timestamp=f"2024-01-0{i + 1}T10:00:00",
                channel="X",
                holder_engagement=0,
                closer_engagement=0,
                impression_interaction=0,
            )
            for i in range(3)
        ],
    )

    client.compute([j1, j2])

    body = mock_post.call_args.kwargs["json"]
    sessions = body["customer_journeys"]
    assert len(sessions) == 5
    assert [s["conversion_id"] for s in sessions] == ["c1", "c1", "c2", "c2", "c2"]


@patch("adapters.ihc.client.requests.post")
def test_compute_translates_iso_timestamp_to_space_separated_format(mock_post):
    """
    GIVEN a touchpoint with timestamp '2024-01-05T09:00:00'
    WHEN compute is called
    THEN the sent timestamp is '2024-01-05 09:00:00' (the format IHC requires).
    """
    mock_post.return_value = _ok_response()
    client = IhcClient(api_key="KEY", conv_type_id="TYPE")

    client.compute([_journey()])

    sent = mock_post.call_args.kwargs["json"]["customer_journeys"]
    assert sent[0]["timestamp"] == "2024-01-05 09:00:00"


@patch("adapters.ihc.client.requests.post")
def test_compute_sends_every_session_with_conversion_flag_zero(mock_post):
    """
    GIVEN any list of journeys (no synthetic conversion sessions in our domain)
    WHEN compute is called
    THEN every outgoing session has conversion=0; IHC infers the closer from
         the last session per journey.
    """
    mock_post.return_value = _ok_response()
    client = IhcClient(api_key="KEY", conv_type_id="TYPE")

    client.compute([_journey()])

    sent = mock_post.call_args.kwargs["json"]["customer_journeys"]
    assert all(s["conversion"] == 0 for s in sent)


@patch("adapters.ihc.client.requests.post")
def test_compute_returns_typed_response_on_200(mock_post):
    """
    GIVEN a 200 response with one scored session
    WHEN compute is called
    THEN it returns an IhcComputeResponse exposing the typed value entries.
    """
    mock_post.return_value = _ok_response(
        value=[
            {
                "conversion_id": "c1",
                "session_id": "s1",
                "initializer": 1.0,
                "holder": 0.0,
                "closer": 1.0,
                "ihc": 1.0,
            }
        ]
    )
    client = IhcClient(api_key="KEY", conv_type_id="TYPE")

    result = client.compute([_journey()])

    assert isinstance(result, IhcComputeResponse)
    assert result.status_code == 200
    assert len(result.value) == 1
    assert result.value[0].ihc == 1.0
    assert result.partial_failure_errors == []


@patch("adapters.ihc.client.requests.post")
def test_compute_parses_partial_failure_response_206(mock_post):
    """
    GIVEN a 206 response with one success and one partial failure
    WHEN compute is called
    THEN both lists are populated with typed objects; the trigger
         (conversion_id + session_id) and reason are accessible.
    """
    mock_post.return_value = MagicMock(
        status_code=206,
        json=lambda: {
            "statusCode": 206,
            "value": [
                {
                    "conversion_id": "c1",
                    "session_id": "s1",
                    "initializer": 1.0,
                    "holder": 0.0,
                    "closer": 0.5,
                    "ihc": 0.7,
                }
            ],
            "partialFailureErrors": [
                {
                    "trigger": {"conversion_id": "c2", "session_id": "s2"},
                    "reason": "invalid timestamp",
                    "statusCode": 406,
                }
            ],
        },
    )
    client = IhcClient(api_key="KEY", conv_type_id="TYPE")

    result = client.compute([_journey()])

    assert result.status_code == 206
    assert len(result.value) == 1
    assert len(result.partial_failure_errors) == 1
    err = result.partial_failure_errors[0]
    assert err.trigger.conversion_id == "c2"
    assert err.trigger.session_id == "s2"
    assert err.reason == "invalid timestamp"
    assert err.status_code == 406


@patch("adapters.ihc.client.requests.post")
def test_compute_raises_IhcApiError_on_non_2xx(mock_post):
    """
    GIVEN a 500 response from the API
    WHEN compute is called
    THEN IhcApiError is raised carrying the status code and body.
    """
    mock_post.return_value = MagicMock(status_code=500, text="server boom")
    client = IhcClient(api_key="KEY", conv_type_id="TYPE")

    with pytest.raises(IhcApiError) as exc:
        client.compute([_journey()])

    assert exc.value.status_code == 500
    assert "boom" in exc.value.body


@patch("adapters.ihc.client.requests.post")
def test_compute_uses_configurable_base_url(mock_post):
    """
    GIVEN a client constructed with a custom base_url
    WHEN compute is called
    THEN the POST goes to that base_url (enables mocked integration tests
         against a local stub).
    """
    mock_post.return_value = _ok_response()
    client = IhcClient(api_key="KEY", conv_type_id="TYPE", base_url="http://stub.test")

    client.compute([_journey()])

    assert mock_post.call_args.args[0] == "http://stub.test/v1/compute_ihc"
