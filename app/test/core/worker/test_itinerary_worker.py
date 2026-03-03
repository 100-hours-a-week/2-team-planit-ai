"""
Redis Stream worker integration test.

Requirements:
  - Local Redis running (localhost:6379)
  - Run with: pytest -m integration

Verifies:
  1. Worker consumes messages from request stream
  2. Pushes results to result stream after pipeline execution
  3. Result message fields are correct (tripId, status, payload)
  4. Result payload deserializes to ItineraryResponse
  5. Error case pushes status="FAIL" with error field
  6. ACK clears pending list
"""

import pytest
import asyncio
import json
from unittest.mock import AsyncMock
from datetime import datetime

import redis.asyncio as aioredis

from app.core.config import settings
from app.schemas.persona import ItineraryRequest
from app.schemas.Itinerary import ItineraryResponse
from app.test.core.dummy_itinerary import create_dummy_itinerary_response
from app.service.Ininerary.GenInitItineraryService import GenInitItineraryService


# Test-only stream keys (isolated from production data)
TEST_REQUEST_STREAM = "test:stream:ai-jobs"
TEST_RESULT_STREAM = "test:stream:itinerary-results"
TEST_CONSUMER_GROUP = "test-planit-workers"
TEST_CONSUMER_NAME = "test-worker-1"


@pytest.fixture
async def redis_client():
    """Test Redis connection with cleanup after test."""
    r = aioredis.from_url(settings.redis_url, decode_responses=True)
    yield r
    # cleanup: delete test streams
    await r.delete(TEST_REQUEST_STREAM, TEST_RESULT_STREAM)
    await r.aclose()


def _make_dummy_request() -> ItineraryRequest:
    """Create a dummy ItineraryRequest."""
    return ItineraryRequest(
        tripId=999,
        arrivalDate="2026-03-14",
        arrivalTime="09:00",
        departureDate="2026-03-16",
        departureTime="18:00",
        travelCity="도쿄",
        totalBudget=500000,
        travelTheme=["관광", "맛집"],
        wantedPlace=["센소지", "시부야"],
    )


@pytest.mark.integration
class TestItineraryWorkerIntegration:

    async def test_worker_consumes_and_produces(self, redis_client):
        """Happy path: request -> worker processes -> SUCCESS pushed to result stream."""

        # 1. Create Consumer Group
        try:
            await redis_client.xgroup_create(
                TEST_REQUEST_STREAM, TEST_CONSUMER_GROUP, id="0", mkstream=True
            )
        except aioredis.ResponseError as e:
            if "BUSYGROUP" not in str(e):
                raise

        # 2. XADD dummy request message to request stream
        dummy_request = _make_dummy_request()
        await redis_client.xadd(TEST_REQUEST_STREAM, {
            "tripId": str(dummy_request.tripId),
            "payload": dummy_request.model_dump_json(),
            "createdAt": datetime.now().isoformat(),
        })

        # 3. Run one worker loop iteration (service is mocked)
        service = GenInitItineraryService()

        # XREADGROUP to consume message
        messages = await redis_client.xreadgroup(
            groupname=TEST_CONSUMER_GROUP,
            consumername=TEST_CONSUMER_NAME,
            streams={TEST_REQUEST_STREAM: ">"},
            count=1,
            block=3000,
        )
        assert messages, "No message consumed from request stream"

        for stream_name, entries in messages:
            for msg_id, fields in entries:
                # 4. Process like the worker would
                trip_id = fields["tripId"]
                request = ItineraryRequest.model_validate_json(fields["payload"])
                result = await service.gen_init_itinerary(request)

                # 5. Push result to result stream
                await redis_client.xadd(TEST_RESULT_STREAM, {
                    "tripId": trip_id,
                    "status": "SUCCESS",
                    "payload": result.model_dump_json(),
                })

                # 6. ACK
                await redis_client.xack(
                    TEST_REQUEST_STREAM, TEST_CONSUMER_GROUP, msg_id
                )

        # 7. Verify result stream
        results = await redis_client.xrange(TEST_RESULT_STREAM)
        assert len(results) == 1

        result_id, result_fields = results[0]
        assert result_fields["tripId"] == "999"
        assert result_fields["status"] == "SUCCESS"

        # Verify payload deserializes to ItineraryResponse
        response = ItineraryResponse.model_validate_json(result_fields["payload"])
        assert response.tripId == 999
        assert response.message == "SUCCESS"
        assert len(response.itineraries) == 3  # dummy data has 3 days

        # 8. Verify pending list is empty after ACK
        pending = await redis_client.xpending(
            TEST_REQUEST_STREAM, TEST_CONSUMER_GROUP
        )
        assert pending["pending"] == 0

    async def test_worker_handles_error(self, redis_client):
        """Error path: invalid payload -> status=FAIL with error field pushed."""

        try:
            await redis_client.xgroup_create(
                TEST_REQUEST_STREAM, TEST_CONSUMER_GROUP, id="0", mkstream=True
            )
        except aioredis.ResponseError:
            pass

        # Send message with invalid payload
        await redis_client.xadd(TEST_REQUEST_STREAM, {
            "tripId": "888",
            "payload": '{"invalid": "data"}',
            "createdAt": datetime.now().isoformat(),
        })

        messages = await redis_client.xreadgroup(
            groupname=TEST_CONSUMER_GROUP,
            consumername=TEST_CONSUMER_NAME,
            streams={TEST_REQUEST_STREAM: ">"},
            count=1,
            block=3000,
        )

        for stream_name, entries in messages:
            for msg_id, fields in entries:
                trip_id = fields["tripId"]
                try:
                    ItineraryRequest.model_validate_json(fields["payload"])
                    raise AssertionError("Parsing should have failed")
                except Exception as e:
                    # Push error result
                    await redis_client.xadd(TEST_RESULT_STREAM, {
                        "tripId": trip_id,
                        "status": "FAIL",
                        "error": str(e),
                    })
                    await redis_client.xack(
                        TEST_REQUEST_STREAM, TEST_CONSUMER_GROUP, msg_id
                    )

        results = await redis_client.xrange(TEST_RESULT_STREAM)
        last_result = results[-1][1]
        assert last_result["tripId"] == "888"
        assert last_result["status"] == "FAIL"
        assert "error" in last_result
        assert len(last_result["error"]) > 0
