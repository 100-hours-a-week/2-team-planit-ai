from typing import Dict, List, Optional, Any
import asyncio
import json
import logging
import re
from datetime import datetime
from pathlib import Path
from langgraph.graph import StateGraph, END
from app.core.models.PoiAgentDataclass.poi import (
    PoiAgentState,
    PoiSearchResult,
    PoiInfo,
    PoiData,
    PoiValidationError,
    PoiSearchStats,
    _convert_poi_info_to_data,
)

logger = logging.getLogger(__name__)
from app.core.Agents.Poi.PoiMapper.BasePoiMapper import BasePoiMapper
from app.core.Agents.Poi.PoiMapper.GoogleMapsPoiMapper import GoogleMapsPoiMapper
from app.core.LLMClient.BaseLlmClient import BaseLLMClient
from app.core.Agents.Poi.QueryExtention.QueryExtention import QueryExtension
from app.core.Agents.Poi.WebSearch.WebSearchAgent import WebSearchAgent
from app.core.Agents.Poi.VectorDB.BaseVectorSearchAgent import BaseVectorSearchAgent
from app.core.Agents.Poi.VectorDB.VectorSearchAgent import VectorSearchAgent
from app.core.Agents.Poi.ResultMerger import ResultMerger
from app.core.Agents.Poi.InfoSummaizeAgent import InfoSummarizeAgent
from app.core.Agents.Poi.VectorDB.EmbeddingPipeline.EmbeddingPipeline import EmbeddingPipeline
from app.core.Agents.Poi.Reranker.Reranker import Reranker
from app.core.Agents.Poi.PoiAliasCache import PoiAliasCache
from app.core.Agents.Poi.WebSearch.Extractor.JinaReader import JinaReader
from app.core.Agents.Poi.WebSearch.Extractor.LangExtractor import LangExtractor
from app.core.Agents.Poi.PoiMapper.GoogleMapsPoiMapper import GoogleMapsPoiMapper


class PoiGraph:
    """
    POI 검색 워크플로우 그래프 (VectorDB-first 전략)

    페르소나 기반으로 키워드를 추출하고,
    VectorDB를 우선 조회하여 관련도 높은 결과를 먼저 확보합니다.
    VectorDB 결과가 충분하면 웹 검색을 스킵하고,
    부족한 경우에만 웹 검색을 추가로 진행합니다.
    """
    
    def __init__(
        self,
        llm_client: BaseLLMClient,
        rerank_min_score: float, # 리랭커에서 최소 점수 임계값 (이하는 버림)
        keyword_k: int,     # 키워드 추출에서 상위 N개를 선택 그 이하는 버림
        embedding_k: int,   # 임베딩 검색에서 상위 N개를 선택 그 이하는 버림
        web_search_k: int,  # 웹 검색에서 상위 N개를 선택 그 이하는 버림
        final_poi_count: int, # 최종 POI 개수
        vector_db_path: Optional[str] = None,  # None이면 app/data/vector_db/ 사용
        web_weight: float = 0.6,
        embedding_weight: float = 0.4,
        vector_search_agent: Optional[BaseVectorSearchAgent] = None,
    ):
        """
        총 검색 갯수는 keyword_k * web_search_k 입니다.
        결과는 장담 받을 수 없음
        langextractor로 결과가 가져온 갯수 만큼 Mapping 
        """
        # 컴포넌트 초기화
        self.keyword_extractor = QueryExtension(llm_client)
        self.extractor = LangExtractor()
        self.jina_reader = JinaReader()
        # Google Maps API 키 설정
        self.web_search = WebSearchAgent(
            extractor=self.extractor,
            jina_reader=self.jina_reader,
            num_results=web_search_k
        )

        if vector_search_agent is not None:
            self.vector_search = vector_search_agent
            self.embedding_pipeline = vector_search_agent.embedding_pipeline
        else:
            self.embedding_pipeline = EmbeddingPipeline()
            self.vector_search = VectorSearchAgent(
                embedding_pipeline=self.embedding_pipeline,
                persist_directory=vector_db_path
            )
        self.result_merger = ResultMerger(
            web_weight=web_weight,
            embedding_weight=embedding_weight
        )
        self.info_summarizer = InfoSummarizeAgent(llm_client)
        self.reranker = Reranker(llm_client, min_score=rerank_min_score)
        self.alias_cache = PoiAliasCache()
        self.keyword_k = keyword_k
        self.web_search_k = web_search_k
        self.embedding_k = embedding_k
        self.final_poi_count = final_poi_count
        
        # POI Mapper 초기화 (Google Maps API 검증용)
        self.poi_mapper: Optional[BasePoiMapper] = GoogleMapsPoiMapper()
        
        # 통계 추적용
        self._stats: Optional[PoiSearchStats] = None
        
        # 그래프 빌드
        self.graph = self._build_graph()
    
    def _build_graph(self):
        """LangGraph 워크플로우 빌드

        Flow Architecture (VectorDB-first):
        1. extract_keywords: 페르소나에서 키워드 추출
        2. vector_db_first_search: VectorDB 우선 조회 (관련도 >= 0.9)
        3. rerank_embedding: VectorDB 결과 리랭킹
        4. [conditional] _check_poi_sufficiency:
           - sufficient (>= final_poi_count): → merge_results → END
           - insufficient (< final_poi_count): → web_search → process_and_rerank_web → merge_results → END
        """
        workflow = StateGraph(PoiAgentState)

        # 노드 추가
        workflow.add_node("extract_keywords", self._extract_keywords)
        workflow.add_node("vector_db_first_search", self._vector_db_first_search)
        workflow.add_node("rerank_embedding", self._rerank_embedding)
        workflow.add_node("web_search", self._web_search)
        workflow.add_node("process_and_rerank_web", self._process_and_rerank_web)
        workflow.add_node("merge_results", self._merge_results)

        # 순차 흐름: 키워드 → VectorDB 조회 → 리랭킹
        workflow.set_entry_point("extract_keywords")
        workflow.add_edge("extract_keywords", "vector_db_first_search")
        workflow.add_edge("vector_db_first_search", "rerank_embedding")

        # 리랭킹 후 조건 분기
        workflow.add_conditional_edges(
            "rerank_embedding",
            self._check_poi_sufficiency,
            {
                "sufficient": "merge_results",
                "insufficient": "web_search"
            }
        )

        # 웹 검색 경로
        workflow.add_edge("web_search", "process_and_rerank_web")
        workflow.add_edge("process_and_rerank_web", "merge_results")

        # 병합 후 종료
        workflow.add_edge("merge_results", END)

        return workflow.compile()
    
    async def _extract_keywords(self, state: PoiAgentState) -> dict:
        """페르소나에서 키워드 추출 노드"""
        keywords = await self.keyword_extractor.extract_keywords(
            persona_summary=state["persona_summary"],
            destination=state["travel_destination"],
            start_date=state["start_date"],
            end_date=state["end_date"]
        )
        logger.info(f"키워드 추출 완료: {len(keywords)}개 키워드")
        logger.info(f"추출된 키워드: {keywords}")
        return {"keywords": keywords}
    
    @staticmethod
    def _normalize_poi_name(name: str) -> str:
        """POI 이름 정규화 (중복 비교용)
        
        - 연속 공백을 단일 공백으로
        - 양쪽 공백 제거
        - 소문자 변환
        """
        if not name:
            return ""
        normalized = re.sub(r'\s+', ' ', name.strip())
        return normalized.lower()

    async def _web_search(self, state: PoiAgentState) -> dict:
        """웹 검색 노드"""
        keywords = state.get("keywords", [])
        if not keywords:
            return {"web_results": []}

        logger.info(f"웹 검색 시작: {self.keyword_k}개 키워드 사용")
        logger.info(f"웹 검색 키워드: {keywords[:self.keyword_k]}")
        travel_destination = state.get("travel_destination", "")
        
        # stats 객체 전달하여 통계 수집
        results = await self.web_search.search_multiple(
            keywords[:self.keyword_k],
            destination=travel_destination,
            stats=self._stats
        )

        # === 1차 중복 제거: title 기준 (LangExtractor 결과 내 중복) ===
        seen_titles: set = set()
        unique_results: List[PoiSearchResult] = []
        for result in results:
            normalized_title = self._normalize_poi_name(result.title)
            if normalized_title not in seen_titles:
                seen_titles.add(normalized_title)
                unique_results.append(result)
            else:
                logger.info(f"1차 중복 제거 (title): {result.title}")

        for result in unique_results:
            logger.info(f"웹 검색 결과: {result.title}")
        
        logger.info(f"1차 중복 제거: {len(results)}개 -> {len(unique_results)}개")
        
        # 통계 수집: 전체 POI 통계 (웹 검색)
        if self._stats is not None:
            self._stats["web_raw_poi_count"] = len(results)
            self._stats["web_dup_removed"] = len(results) - len(unique_results)
            self._stats["web_final_poi_count"] = len(unique_results)
        
        return {"web_results": unique_results}

    async def _process_and_rerank_web(self, state: PoiAgentState) -> dict:
        """
        웹 검색 결과를 배치로 처리 + 리랭킹하는 통합 노드.

        10개씩 배치로 나누어:
        1. 개별 POI 요약 (InfoSummarizeAgent)
        2. Google Maps 검증 (PoiMapper)
        3. VectorDB 저장
        4. 리랭킹
        5. relevance_score >= 0.5인 결과가 20개 이상이면 조기 종료
        """
        web_results = state.get("web_results", [])
        persona_summary = state["persona_summary"]
        travel_destination = state["travel_destination"]

        if not web_results:
            return {"reranked_web_results": [], "poi_data_map": {}}

        BATCH_SIZE = 10
        MIN_SCORE = 0.5
        travel_days = state.get("travel_days", 0)
        TARGET_COUNT = travel_days * 10 if travel_days > 0 else 20

        all_reranked: List[PoiSearchResult] = []
        all_poi_data: Dict[str, PoiData] = {}
        semaphore = asyncio.Semaphore(5)
        
        # 통계 추적용 카운터
        vectordb_hit_count = 0
        mapper_processed_count = 0
        total_checked = 0
        summarize_failed_count = 0
        mapper_failed_count = 0
        other_error_count = 0
        rerank_pre_count = 0
        rerank_post_count = 0
        rerank_dropped_items: List[tuple] = []  # (title, score)

        for batch_start in range(0, len(web_results), BATCH_SIZE):
            batch = web_results[batch_start:batch_start + BATCH_SIZE]
            logger.info(f"배치 처리 시작: {batch_start + 1}~{batch_start + len(batch)} / {len(web_results)}")

            # --- 1) 배치 내 개별 POI 처리 ---
            processed_batch: List[PoiSearchResult] = []
            batch_poi_data: List[PoiData] = []

            async def process_single_poi(poi_result: PoiSearchResult) -> Optional[tuple]:
                """Returns (PoiSearchResult, PoiData, is_vectordb_hit) or error tuple"""
                async with semaphore:
                    try:
                        poi_info = await self.info_summarizer.summarize_single(
                            poi_result=poi_result,
                            persona_summary=persona_summary
                        )
                        if not poi_info:
                            logger.warning(f"POI 요약 실패 (summarize_single): {poi_result}")
                            return ("SUMMARIZE_FAILED", None, None)

                        normalized_name = self._normalize_poi_name(poi_info.name)

                        # === 1단계: 별칭 캐시에서 이름 조회 ===
                        cached_place_id = await self.alias_cache.find_by_name(
                            normalized_name, travel_destination
                        )
                        if cached_place_id:
                            existing_poi = await self.vector_search.find_by_google_place_id(
                                cached_place_id, city_filter=travel_destination
                            )
                            if existing_poi:
                                logger.info(f"별칭 캐시 히트: {poi_info.name} → place_id={cached_place_id}")
                                search_result = PoiSearchResult(
                                    poi_id=existing_poi.id,
                                    title=poi_result.title,
                                    snippet=poi_result.snippet,
                                    url=poi_result.url,
                                    source=poi_result.source,
                                    relevance_score=poi_result.relevance_score
                                )
                                return (search_result, existing_poi, True)

                        # === 2단계: Mapper 호출 ===
                        try:
                            poi_data = await self.poi_mapper.map_poi(
                                poi_info=poi_info,
                                city=travel_destination,
                                source_url=poi_result.url,
                                raise_on_failure=True
                            )
                        except PoiValidationError as e:
                            logger.warning(f"POI 검증 실패(Google Maps): {e}")
                            logger.warning(f"             {poi_result}")
                            return ("MAPPER_FAILED", None, None)

                        if not poi_data:
                            return ("MAPPER_FAILED", None, None)

                        # === 3단계: Mapper 결과의 place_id로 별칭 확인 ===
                        if poi_data.google_place_id:
                            is_alias = await self.alias_cache.has_place_id(
                                poi_data.google_place_id
                            )
                            if is_alias:
                                # 다른 이름의 같은 장소 → 별칭 등록
                                logger.info(f"별칭 감지: {poi_info.name} → 기존 place_id={poi_data.google_place_id}")
                                await self.alias_cache.add(
                                    normalized_name, travel_destination,
                                    poi_data.google_place_id
                                )
                                existing_poi = await self.vector_search.find_by_google_place_id(
                                    poi_data.google_place_id
                                )
                                if existing_poi:
                                    search_result = PoiSearchResult(
                                        poi_id=existing_poi.id,
                                        title=poi_result.title,
                                        snippet=poi_result.snippet,
                                        url=poi_result.url,
                                        source=poi_result.source,
                                        relevance_score=poi_result.relevance_score
                                    )
                                    return (search_result, existing_poi, True)

                            # 새 POI → 별칭 캐시에 등록
                            await self.alias_cache.add(
                                normalized_name, travel_destination,
                                poi_data.google_place_id
                            )

                        search_result = PoiSearchResult(
                            poi_id=poi_data.id,
                            title=poi_result.title,
                            snippet=poi_result.snippet,
                            url=poi_result.url,
                            source=poi_result.source,
                            relevance_score=poi_result.relevance_score
                        )
                        return (search_result, poi_data, False)  # Mapper 처리
                    except Exception as e:
                        logger.error(f"POI 처리 중 오류: {poi_result.title} - {e}")
                        return ("OTHER_ERROR", None, None)

            tasks = [process_single_poi(r) for r in batch]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            for result in results:
                if isinstance(result, tuple) and len(result) == 3:
                    error_code, data1, data2 = result
                    if error_code == "SUMMARIZE_FAILED":
                        summarize_failed_count += 1
                    elif error_code == "MAPPER_FAILED":
                        mapper_failed_count += 1
                    elif error_code == "OTHER_ERROR":
                        other_error_count += 1
                    elif isinstance(error_code, PoiSearchResult):
                        # 성공: (PoiSearchResult, PoiData, is_vectordb_hit)
                        processed_batch.append(error_code)
                        batch_poi_data.append(data1)
                        if data2:  # is_vectordb_hit
                            vectordb_hit_count += 1
                        else:
                            mapper_processed_count += 1
                elif isinstance(result, Exception):
                    logger.error(f"POI 처리 예외: {result}")
                    other_error_count += 1
            
            total_checked += len(batch)

            # VectorDB 저장
            if batch_poi_data:
                try:
                    await self.vector_search.add_pois_batch(batch_poi_data)
                    logger.info(f"VectorDB 저장 완료: {len(batch_poi_data)}개 POI")
                except Exception as e:
                    logger.error(f"VectorDB 저장 실패: {e}")

            for pd in batch_poi_data:
                all_poi_data[pd.id] = pd

            # --- 2) 배치 리랭킹 ---
            if processed_batch:
                rerank_pre_count += len(processed_batch)
                batch_dropped: list = []
                reranked_batch = await self.reranker.rerank(
                    processed_batch, persona_summary, dropped_out=batch_dropped
                )
                rerank_post_count += len(reranked_batch)
                rerank_dropped_items.extend(batch_dropped)

                all_reranked.extend(reranked_batch)

            # --- 3) 조기 종료 검사 ---
            good_count = sum(1 for r in all_reranked if r.relevance_score >= MIN_SCORE)
            logger.info(f"배치 완료: 누적 {len(all_reranked)}개, 양호(>={MIN_SCORE}) {good_count}개")

            if good_count >= TARGET_COUNT:
                logger.info(f"목표 달성 ({good_count}>={TARGET_COUNT}), 조기 종료")
                # 통계: 조기 종료로 스킵된 POI 수
                if self._stats is not None:
                    remaining = len(web_results) - (batch_start + len(batch))
                    self._stats["early_termination_checked"] = total_checked
                    self._stats["early_termination_skipped"] = remaining
                break

        all_reranked.sort(key=lambda x: x.relevance_score, reverse=True)
        logger.info(f"웹 결과 처리+리랭킹 완료: {len(all_reranked)}개 (전체 {len(web_results)}개 중)")
        
        # 통계 수집: VectorDB 히트 vs Mapper 처리
        if self._stats is not None:
            self._stats["vectordb_hit_count"] = vectordb_hit_count
            self._stats["mapper_processed_count"] = mapper_processed_count
            # 실패 통계
            self._stats["summarize_failed_count"] = summarize_failed_count
            self._stats["mapper_failed_count"] = mapper_failed_count
            self._stats["other_error_count"] = other_error_count
            # 리랭커 탈락 통계
            self._stats["rerank_pre_count"] = rerank_pre_count
            self._stats["rerank_post_count"] = rerank_post_count
            self._stats["rerank_dropped_count"] = rerank_pre_count - rerank_post_count
            self._stats["rerank_dropped_items"] = rerank_dropped_items
            # 조기 종료가 없었으면 전체 검사
            if "early_termination_checked" not in self._stats:
                self._stats["early_termination_checked"] = total_checked
                self._stats["early_termination_skipped"] = 0
        
        return {"reranked_web_results": all_reranked, "poi_data_map": all_poi_data}

    async def _vector_db_first_search(self, state: PoiAgentState) -> dict:
        """VectorDB 우선 조회 노드

        VectorDB에서 관련도 0.55 이상인 결과만 필터링하여 반환.
        travel_destination이 있으면 해당 도시로 필터링하여 검색.
        metadata에서 PoiData를 복원하여 poi_data_map에 추가.
        """
        RELEVANCE_THRESHOLD = 0.3

        keywords = state.get("keywords", [])
        travel_destination = state.get("travel_destination", "")

        logger.info(f"VectorDB 우선 조회 시작: {len(keywords)}개 키워드 사용")

        all_pairs: list = []
        pairs = await self.vector_search.search_by_text_with_data(
            query=state.get("persona_summary", ", ".join(keywords)),
            k=self.embedding_k,
            city_filter=travel_destination
        )
        all_pairs.extend(pairs)

        # 중복 제거 (poi_id 기준) + 관련도 threshold 필터링
        seen_ids: set = set()
        filtered_results: List[PoiSearchResult] = []
        embedding_poi_data_map: Dict[str, PoiData] = {}
        for search_result, poi_data in all_pairs:
            if search_result.poi_id and search_result.poi_id not in seen_ids:
                seen_ids.add(search_result.poi_id)
                if search_result.relevance_score >= RELEVANCE_THRESHOLD:
                    filtered_results.append(search_result)
                    embedding_poi_data_map[search_result.poi_id] = poi_data

        logger.info(f"VectorDB 우선 조회: {len(filtered_results)}개 (관련도 >= {RELEVANCE_THRESHOLD})")

        for poi in filtered_results:
            logger.info(f"VectorDB 우선 조회: {poi.title} ({poi.relevance_score})")
        
        # 통계 수집: 임베딩 검색 POI 개수
        if self._stats is not None:
            self._stats["embedding_poi_count"] = len(filtered_results)

        return {
            "embedding_results": filtered_results,
            "poi_data_map": embedding_poi_data_map
        }
    
    async def _rerank_embedding(self, state: PoiAgentState) -> dict:
        """임베딩 검색 결과 리랭킹 노드"""
        embedding_results = state.get("embedding_results", [])
        persona_summary = state["persona_summary"]
        reranked = []

        logger.info(f"rerank_embedding 입력: {len(embedding_results)}개")
        for i in range(0, len(embedding_results), 5):
            reranked.extend(await self.reranker.rerank(embedding_results[i:i+5], persona_summary))

        reranked.sort(key=lambda x: x.relevance_score, reverse=True)
        logger.info(f"rerank_embedding 출력: {len(reranked)}개")
        return {"reranked_embedding_results": reranked}

    def _check_poi_sufficiency(self, state: PoiAgentState) -> str:
        """VectorDB 리랭킹 결과가 충분한지 판정하는 조건부 라우터

        reranked_embedding_results 개수가 final_poi_count 이상이면 'sufficient',
        미만이면 'insufficient'를 반환하여 웹 검색 여부를 결정.
        """
        reranked = state.get("reranked_embedding_results", [])
        count = len(reranked)
        target = state.get("final_poi_count", self.final_poi_count)
        if count >= target:
            logger.info(f"POI 충분: {count}개 >= {target}개 (웹 검색 스킵)")
            return "sufficient"
        else:
            logger.info(f"POI 부족: {count}개 < {target}개 (웹 검색 진행)")
            return "insufficient"

    async def _merge_results(self, state: PoiAgentState) -> dict:
        """결과 병합 노드 (리랭킹된 결과 사용)

        새 플로우에서는 웹 검색 결과가 이미 process_web_results에서
        PoiInfo로 변환되고 VectorDB에 저장된 상태입니다.
        여기서는 양쪽 결과를 병합하고, poi_data_map에서 PoiData를 조회하여
        최종 List[PoiData]를 생성합니다.
        """
        web_reranked = state.get("reranked_web_results", [])
        emb_reranked = state.get("reranked_embedding_results", [])
        logger.info(f"merge 입력 - 웹: {len(web_reranked)}개, 임베딩: {len(emb_reranked)}개")

        merged = self.result_merger.merge(
            web_results=web_reranked,
            embedding_results=emb_reranked,
            stats=self._stats
        )
        logger.info(f"merge 출력 (중복 제거 후): {len(merged)}개")
        
        # 통계 수집: 병합 전후 POI 수
        if self._stats is not None:
            self._stats["pre_merge_web_count"] = len(web_reranked)
            self._stats["pre_merge_embedding_count"] = len(emb_reranked)
            self._stats["post_merge_count"] = len(merged)

        # 최종 POI 개수 제한
        # merged = merged[:self.final_poi_count]

        # poi_data_map에서 PoiData 조회하여 최종 리스트 생성
        poi_data_map = state.get("poi_data_map", {})

        # === 중복 POI 별칭 DB 등록 ===
        merge_dup_pairs = self._stats.get("merge_dup_pairs", []) if self._stats else []
        travel_destination = state.get("travel_destination", "")
        alias_registered_count = 0

        for pair in merge_dup_pairs:
            dup_title = pair.get("title", "")
            existing_poi_id = pair.get("poi_id", "")

            if not dup_title or not existing_poi_id:
                continue

            poi_data = poi_data_map.get(existing_poi_id)
            if poi_data and poi_data.google_place_id:
                await self.alias_cache.add(
                    dup_title, travel_destination, poi_data.google_place_id
                )
                logger.info(
                    f"별칭 DB 등록 (merge 중복): {dup_title} → {poi_data.google_place_id}"
                )
                alias_registered_count += 1

        if alias_registered_count > 0:
            logger.info(f"merge 단계에서 별칭 DB에 {alias_registered_count}개 등록 완료")
        final_poi_data: List[PoiData] = []

        for result in merged:
            if result.poi_id and result.poi_id in poi_data_map:
                final_poi_data.append(poi_data_map[result.poi_id])
            else:
                logger.warning(f"PoiData not found for poi_id: {result.poi_id}, title: {result.title}")
        return {"merged_results": merged, "final_poi_data": final_poi_data}
    
    async def run(
        self,
        persona_summary: str,
        travel_destination: str,
        start_date: str = "",
        end_date: str = "",
        save_path: Optional[str] = None
    ) -> List[PoiData]:
        """
        POI 검색 워크플로우 실행 (VectorDB-first 전략)

        Flow:
        1. 키워드 추출
        2. VectorDB 우선 조회 (관련도 >= 0.9 필터링)
        3. VectorDB 결과 리랭킹
        4. 충분성 판정 (>= final_poi_count)
           - 충분: 바로 merge → 최종 결과
           - 부족: 웹 검색 → 웹 결과 처리/리랭킹 → merge → 최종 결과
        5. poi_data_map에서 PoiData 조회하여 최종 List[PoiData] 반환

        Args:
            persona_summary: 사용자 페르소나 요약
            travel_destination: 사용자가 여행하는 지역
            start_date: 여행 시작일 (YYYY-MM-DD)
            end_date: 여행 종료일 (YYYY-MM-DD)
            save_path: JSON 저장 경로 (선택적)

        Returns:
            최종 POI 데이터 목록 (List[PoiData], Google Maps 검증 완료)
        """
        logger.info(f"POI Graph 실행 시작: {travel_destination}, {persona_summary[:50]}...")

        # 통계 초기화
        self._stats: PoiSearchStats = {}

        # 여행일수 계산 → 동적 POI 갯수 설정
        travel_days = None
        if start_date and end_date:
            try:
                sd = datetime.strptime(start_date, "%Y-%m-%d")
                ed = datetime.strptime(end_date, "%Y-%m-%d")
                travel_days = (ed - sd).days + 1
                if travel_days < 1:
                    travel_days = None
            except ValueError:
                travel_days = None

        dynamic_poi_count = travel_days * 5 if travel_days else self.final_poi_count
        logger.info(f"여행일수={travel_days}, dynamic_poi_count={dynamic_poi_count}")

        initial_state: PoiAgentState = {
            "travel_destination": travel_destination,
            "persona_summary": persona_summary,
            "start_date": start_date,
            "end_date": end_date,
            "keywords": [],
            "web_results": [],
            "embedding_results": [],
            "reranked_web_results": [],
            "reranked_embedding_results": [],
            "merged_results": [],
            "poi_data_map": {},
            "final_poi_data": [],
            "final_pois": [],
            "final_poi_count": dynamic_poi_count,
            "travel_days": travel_days or 0,
        }

        result = await self.graph.ainvoke(initial_state)

        # 디버그 로깅
        for key, value in result.items():
            if isinstance(value, list):
                logger.info(f"{key}: {len(value)}개")
            elif isinstance(value, dict):
                logger.info(f"{key}: {len(value)}개")

        # 최종 결과는 final_poi_data (List[PoiData])
        final_poi_data = result.get("final_poi_data", [])

        logger.info(f"POI Graph 실행 완료: 총 {len(final_poi_data)}개 POI 반환")
        
        # 통계 보고서 출력
        self._print_search_report()

        # JSON 저장 (요청 시)
        if save_path:
            self.save_state_to_json(result, save_path)

        return final_poi_data, result
    
    @staticmethod
    def _serialize_item(item: Any) -> Any:
        """Pydantic 모델과 Enum을 직렬화"""
        if hasattr(item, 'model_dump'):
            # Pydantic 모델 -> dict로 변환
            dumped = item.model_dump()
            # Enum 값들을 재귀적으로 처리
            return PoiGraph._serialize_item(dumped)
        elif hasattr(item, 'value'):  # Enum
            return item.value
        elif isinstance(item, list):
            return [PoiGraph._serialize_item(i) for i in item]
        elif isinstance(item, dict):
            return {k: PoiGraph._serialize_item(v) for k, v in item.items()}
        return item

    def save_state_to_json(self, state: PoiAgentState, file_path: str) -> bool:
        """
        PoiAgentState 전체를 JSON 파일로 저장
        
        Args:
            state: 저장할 전체 상태
            file_path: 저장할 파일 경로
        
        Returns:
            저장 성공 여부
        """
        try:
            output = {
                "metadata": {
                    "generated_at": datetime.now().isoformat()
                },
                **{key: self._serialize_item(value) for key, value in state.items()}
            }
            
            Path(file_path).parent.mkdir(parents=True, exist_ok=True)
            
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(output, f, ensure_ascii=False, indent=2, default=str)
            
            logger.info(f"JSON 저장 성공: {file_path}")
            return True
            
        except Exception as e:
            logger.error(f"JSON 저장 실패: {e}")
            return False

    def _print_search_report(self) -> None:
        """POI 검색 통계 보고서를 로그로 출력"""
        if self._stats is None:
            logger.warning("통계 데이터가 없습니다.")
            return
        
        s = self._stats
        
        # 구분선
        separator = "=" * 80
        
        lines = [
            "",
            separator,
            "                        📊 POI 검색 통계 보고서",
            separator,
            "",
            f"[0] 임베딩(VectorDB) 검색 POI: {s.get('embedding_poi_count', 0)}개",
            "",
        ]
        
        # [1] 웹 검색 키워드
        keywords = s.get("keywords", [])
        lines.append(f"[1] 웹 검색 키워드: {s.get('keyword_count', len(keywords))}개")
        if keywords:
            lines.append(f"    - {', '.join(keywords)}")
        lines.append("")
        
        # [2] 키워드별 검색된 웹 페이지
        pages_per_keyword = s.get("pages_per_keyword", {})
        if pages_per_keyword:
            lines.append("[2] 키워드별 검색된 웹 페이지:")
            for kw, count in pages_per_keyword.items():
                lines.append(f"    - {kw}: {count}페이지")
        else:
            lines.append("[2] 키워드별 검색된 웹 페이지: (데이터 없음)")
        lines.append("")
        
        # [3] 캐시 처리 통계
        cache_hit = s.get("cache_hit_pages", 0)
        total_pages = s.get("total_pages", 0)
        cache_percent = (cache_hit / total_pages * 100) if total_pages > 0 else 0
        lines.append(f"[3] 캐시로 처리된 웹 페이지: {cache_hit}개 / {total_pages}개 ({cache_percent:.1f}%)")
        lines.append("")
        
        # [4] 웹 페이지별 추출 POI
        pages_poi_stats = s.get("pages_poi_stats", [])
        if pages_poi_stats:
            # 상태별 카운트
            success_count = sum(1 for p in pages_poi_stats if p.get("status") == "success")
            cache_count = sum(1 for p in pages_poi_stats if p.get("status") == "cache")
            jina_failed_count = sum(1 for p in pages_poi_stats if p.get("status") == "jina_failed")
            empty_count = sum(1 for p in pages_poi_stats if p.get("status") == "empty")
            
            lines.append(f"[4] 웹 페이지별 추출 POI: (성공 {success_count}, 캐시 {cache_count}, Jina실패 {jina_failed_count}, 빈결과 {empty_count})")
            for page in pages_poi_stats[:10]:  # 최대 10개까지만 표시
                url_short = page["url"][:60] + "..." if len(page["url"]) > 60 else page["url"]
                status = page.get("status", "success")
                if status == "success":
                    lines.append(f"    - {url_short}")
                    lines.append(f"      원본 {page['raw_count']}개 → 중복 {page['dup_count']}개 → 최종 {page['final_count']}개")
                elif status == "cache":
                    lines.append(f"    - {url_short} (캐시)")
                    lines.append(f"      최종 {page['final_count']}개")
                elif status == "jina_failed":
                    lines.append(f"    - {url_short} (Jina 실패)")
                elif status == "empty":
                    lines.append(f"    - {url_short} (POI 없음)")
            if len(pages_poi_stats) > 10:
                lines.append(f"    ... 외 {len(pages_poi_stats) - 10}개 페이지")
        else:
            lines.append("[4] 웹 페이지별 추출 POI: (데이터 없음)")
        lines.append("")
        
        # [5] 전체 POI 통계 (웹 검색)
        web_raw = s.get("web_raw_poi_count", 0)
        web_dup = s.get("web_dup_removed", 0)
        web_final = s.get("web_final_poi_count", 0)
        lines.append("[5] 전체 POI (웹 검색):")
        lines.append(f"    - 원본: {web_raw}개 → 중복 제거: {web_dup}개 → 최종: {web_final}개")
        lines.append("")
        
        # [6] 별칭 캐시 vs Mapper 처리
        alias_hit = s.get("vectordb_hit_count", 0)  # 실제로는 별칭 캐시 히트
        mapper = s.get("mapper_processed_count", 0)
        lines.append("[6] 별칭 캐시 vs Mapper 처리:")
        lines.append(f"    - 별칭 캐시 히트 (Mapper 스킵): {alias_hit}개")
        lines.append(f"    - Mapper 처리: {mapper}개")
        lines.append("")
        
        # [7] 조기 종료 통계
        early_checked = s.get("early_termination_checked", 0)
        early_skipped = s.get("early_termination_skipped", 0)
        lines.append("[7] 조기 종료:")
        lines.append(f"    - 검사한 POI: {early_checked}개")
        lines.append(f"    - 조기 종료로 스킵: {early_skipped}개")
        lines.append("")
        
        # [7-1] POI 처리 실패 통계
        summarize_failed = s.get("summarize_failed_count", 0)
        mapper_failed = s.get("mapper_failed_count", 0)
        other_error = s.get("other_error_count", 0)
        total_failed = summarize_failed + mapper_failed + other_error
        total_success = s.get("vectordb_hit_count", 0) + s.get("mapper_processed_count", 0)
        lines.append(f"[7-1] POI 처리 실패 통계: 총 {total_failed}개 탈락")
        lines.append(f"    - 요약 실패: {summarize_failed}개")
        lines.append(f"    - Google Maps 검증 실패: {mapper_failed}개")
        lines.append(f"    - 기타 오류: {other_error}개")
        lines.append(f"    - 성공: {total_success}개")
        lines.append("")

        # [7-2] 리랭커 탈락 통계
        rerank_pre = s.get("rerank_pre_count", 0)
        rerank_post = s.get("rerank_post_count", 0)
        rerank_dropped = s.get("rerank_dropped_count", 0)
        rerank_dropped_items = s.get("rerank_dropped_items", [])
        lines.append(f"[7-2] 리랭커 필터링 (min_score 미만 탈락):")
        lines.append(f"    - 리랭킹 전: {rerank_pre}개 → 리랭킹 후: {rerank_post}개 (탈락: {rerank_dropped}개)")
        if rerank_dropped_items:
            lines.append(f"    - 탈락 POI 목록:")
            for name, score in rerank_dropped_items:
                lines.append(f"      • {name} (점수: {score:.2f})")
        lines.append("")

        # [8] 병합 전후
        pre_web = s.get("pre_merge_web_count", 0)
        pre_emb = s.get("pre_merge_embedding_count", 0)
        post_merge = s.get("post_merge_count", 0)
        lines.append("[8] 병합 전후:")
        lines.append(f"    - 웹 검색: {pre_web}개")
        lines.append(f"    - 임베딩 검색: {pre_emb}개")
        lines.append(f"    - 최종 병합: {post_merge}개")
        lines.append("")
        
        # [8-1] 병합 중복 제거 상세
        merge_web_dup = s.get("merge_web_dup_count", 0)
        merge_emb_dup = s.get("merge_emb_dup_count", 0)
        merge_total_dup = s.get("merge_total_dup_count", 0)
        merge_web_dup_names = s.get("merge_web_dup_names", [])
        merge_emb_dup_names = s.get("merge_emb_dup_names", [])
        if merge_total_dup > 0:
            lines.append(f"[8-1] 병합 중복 제거: 총 {merge_total_dup}개 (점수 합산)")
            if merge_web_dup > 0:
                lines.append(f"    - 웹 검색 내 중복 (poi_id 기준): {merge_web_dup}개")
                for name in merge_web_dup_names[:5]:  # 최대 5개까지
                    lines.append(f"      • {name}")
                if len(merge_web_dup_names) > 5:
                    lines.append(f"      ... 외 {len(merge_web_dup_names) - 5}개")
            if merge_emb_dup > 0:
                lines.append(f"    - 웹↔임베딩 중복: {merge_emb_dup}개")
                for name in merge_emb_dup_names[:5]:  # 최대 5개까지
                    lines.append(f"      • {name}")
                if len(merge_emb_dup_names) > 5:
                    lines.append(f"      ... 외 {len(merge_emb_dup_names) - 5}개")
            lines.append("")
        
        lines.append(separator)
        lines.append("")
        
        # 로거로 출력
        for line in lines:
            logger.info(line)
