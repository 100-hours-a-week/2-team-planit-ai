"""
일정 생성 워커 - Redis Stream Consumer

Consumer Group 기반으로 stream:ai-jobs 스트림에서 메시지를 소비하고,
파이프라인(페르소나 → POI → 일정) 실행 후 결과를 stream:itinerary-results 스트림에 push.

클라이언트 메시지 포맷:
    fields = {"tripId": "123", "payload": "{...ItineraryRequest JSON...}", "createdAt": "..."}

결과 메시지 포맷:
    fields = {"tripId": "123", "status": "success", "payload": "{...ItineraryResponse JSON...}"}

실행:
    python -m app.worker.itinerary_worker

수평 확장:
    REDIS_CONSUMER_NAME=worker-2 python -m app.worker.itinerary_worker
"""
import asyncio
import logging
import signal

from app.core.config import settings
from app.core.redis_client import RedisClient
from app.core.LLMClient.VllmClient import VllmClient
from app.core.LLMClient.LangchainClient import LangchainClient
from app.core.Agents.Persona.TravelPersonaAgent import TravelPersonaAgent
from app.core.Agents.Poi.PoiGraph import PoiGraph
from app.core.Agents.ItineraryPlan.Planner import Planner
from app.core.Agents.Poi.VectorDB.EmbeddingPipeline.EmbeddingPipeline import EmbeddingPipeline
from app.core.Agents.Poi.VectorDB.VectorSearchAgent import VectorSearchAgent
from app.core.Prompt.PersonaAgentPrompt import PERSONA_SYSTEM_PROMPT, PERSONA_GENTERATE_PROMPT
from app.service.Ininerary.gen_init_Ininerary import GenInitItineraryService
from app.schemas.persona import ItineraryRequest

logger = logging.getLogger(__name__)

_shutdown = False


def _build_service() -> GenInitItineraryService:
    """deps.py와 동일한 싱글턴 패턴으로 서비스 의존성 초기화"""
    embedding_pipeline = EmbeddingPipeline()
    vector_search_agent = VectorSearchAgent(
        embedding_pipeline=embedding_pipeline,
    )
    llm_client = VllmClient()
    langchain_client = LangchainClient(
        base_url=settings.vllm_base_url,
    )
    persona_agent = TravelPersonaAgent(
        llm_client=llm_client,
        persona_prompt=PERSONA_GENTERATE_PROMPT,
        system_prompt=PERSONA_SYSTEM_PROMPT,
    )
    poi_graph = PoiGraph(
        llm_client=llm_client,
        rerank_min_score=0.5,
        keyword_k=3,
        embedding_k=5,
        web_search_k=3,
        final_poi_count=15,
        vector_search_agent=vector_search_agent,
    )
    planner = Planner(
        llm_client=llm_client,
        langchain_client=langchain_client,
        poi_graph=poi_graph,
        google_maps_api_key=settings.google_maps_api_key,
    )
    return GenInitItineraryService(
        travel_persona_agent=persona_agent,
        poi_graph=poi_graph,
        planner=planner,
    )


async def run_worker():
    """메인 워커 루프"""
    global _shutdown

    r = await RedisClient.get_instance()
    await RedisClient.ensure_consumer_group(
        settings.redis_request_stream,
        settings.redis_consumer_group,
    )

    service = _build_service()
    logger.info(
        "Worker '%s' 시작 - group='%s', stream='%s'",
        settings.redis_consumer_name,
        settings.redis_consumer_group,
        settings.redis_request_stream,
    )

    while not _shutdown:
        messages = await r.xreadgroup(
            groupname=settings.redis_consumer_group,
            consumername=settings.redis_consumer_name,
            streams={settings.redis_request_stream: ">"},
            count=1,
            block=settings.redis_block_ms,
        )

        if not messages:
            continue

        for stream_name, entries in messages:
            for msg_id, fields in entries:
                trip_id = fields.get("tripId", "unknown")
                try:
                    request = ItineraryRequest.model_validate_json(fields["payload"])
                    logger.info("Job tripId=%s 처리 시작", trip_id)

                    result = await service.gen_init_itinerary(request)

                    result_fields = {
                        "tripId": trip_id,
                        "status": "SUCCESS",
                        "payload": result.model_dump_json(),
                    }
                except Exception as e:
                    logger.exception("Job tripId=%s 처리 실패", trip_id)
                    result_fields = {
                        "tripId": trip_id,
                        "status": "FAIL",
                        "error": str(e),
                    }

                await r.xadd(
                    settings.redis_result_stream,
                    result_fields,
                    maxlen=settings.redis_max_stream_len,
                )
                await r.xack(
                    settings.redis_request_stream,
                    settings.redis_consumer_group,
                    msg_id,
                )
                logger.info(
                    "Job tripId=%s 완료 - status=%s",
                    trip_id,
                    result_fields["status"],
                )

    await RedisClient.close()
    logger.info("Worker 종료")


def _handle_signal(sig, frame):
    global _shutdown
    logger.info("종료 신호 수신 (%s), graceful shutdown 시작", sig)
    _shutdown = True


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)
    asyncio.run(run_worker())


if __name__ == "__main__":
    main()
