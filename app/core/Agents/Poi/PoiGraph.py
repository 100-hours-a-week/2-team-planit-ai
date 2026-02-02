from typing import Dict, List, Optional, Any
import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path
from langgraph.graph import StateGraph, END
from app.core.models.PoiAgentDataclass.poi import (
    PoiAgentState,
    PoiSearchResult,
    PoiInfo,
    PoiData,
    PoiValidationError,
    _convert_poi_info_to_data,
)

logger = logging.getLogger(__name__)
from app.core.Agents.Poi.PoiMapper.BasePoiMapper import BasePoiMapper
from app.core.Agents.Poi.PoiMapper.GoogleMapsPoiMapper import GoogleMapsPoiMapper
from app.core.LLMClient.BaseLlmClient import BaseLLMClient
from app.core.Agents.Poi.QueryExtention.QueryExtention import QueryExtension
from app.core.Agents.Poi.WebSearch.WebSearchAgent import WebSearchAgent
from app.core.Agents.Poi.VectorDB.VectorSearchAgent import VectorSearchAgent
from app.core.Agents.Poi.ResultMerger import ResultMerger
from app.core.Agents.Poi.InfoSummaizeAgent import InfoSummarizeAgent
from app.core.Agents.Poi.VectorDB.EmbeddingPipeline.EmbeddingPipeline import EmbeddingPipeline
from app.core.Agents.Poi.Reranker.Reranker import Reranker
from app.core.Agents.Poi.WebSearch.Extractor.JinaReader import JinaReader
from app.core.Agents.Poi.WebSearch.Extractor.LangExtractor import LangExtractor
from app.core.Agents.Poi.PoiMapper.GoogleMapsPoiMapper import GoogleMapsPoiMapper


class PoiGraph:
    """
    POI 검색 워크플로우 그래프
    
    페르소나 기반으로 키워드를 추출하고,
    웹 검색과 임베딩 검색을 실행한 후 리랭킹하여
    최종 POI 추천 목록을 생성합니다.
    """
    
    def __init__(
        self,
        llm_client: BaseLLMClient,
        rerank_top_n: int, # 리랭커에서 상위 N개를 선택 그 이하는 버림
        keyword_k: int,     # 키워드 추출에서 상위 N개를 선택 그 이하는 버림
        embedding_k: int,   # 임베딩 검색에서 상위 N개를 선택 그 이하는 버림
        web_search_k: int,  # 웹 검색에서 상위 N개를 선택 그 이하는 버림
        final_poi_count: int, # 최종 POI 개수
        vector_db_path: Optional[str] = None,  # None이면 app/data/vector_db/ 사용
        web_weight: float = 0.6,
        embedding_weight: float = 0.4,

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
        self.reranker = Reranker(llm_client, top_n=rerank_top_n)
        self.keyword_k = keyword_k
        self.web_search_k = web_search_k
        self.embedding_k = embedding_k
        self.final_poi_count = final_poi_count
        
        # POI Mapper 초기화 (Google Maps API 검증용)
        self.poi_mapper: Optional[BasePoiMapper] = GoogleMapsPoiMapper()
        
        # 그래프 빌드
        self.graph = self._build_graph()
    
    def _build_graph(self):
        """LangGraph 워크플로우 빌드

        Flow Architecture:
        1. extract_keywords: 페르소나에서 키워드 추출
        2. parallel_search: 웹 검색 + 임베딩 검색 병렬 실행
           - web_search → process_and_rerank_web (배치 처리 + 리랭킹 + 조기 종료)
           - embedding_search → rerank_embedding
        3. merge_results: 결과 병합
        4. END
        """
        workflow = StateGraph(PoiAgentState)

        # 노드 추가
        workflow.add_node("extract_keywords", self._extract_keywords)
        workflow.add_node("web_search", self._web_search)
        workflow.add_node("process_and_rerank_web", self._process_and_rerank_web)
        workflow.add_node("embedding_search", self._embedding_search)
        workflow.add_node("rerank_embedding", self._rerank_embedding)
        workflow.add_node("merge_results", self._merge_results)

        # 엔트리 포인트
        workflow.set_entry_point("extract_keywords")

        # 키워드 추출 후 웹 검색과 임베딩 검색 병렬 실행
        workflow.add_edge("extract_keywords", "web_search")
        workflow.add_edge("extract_keywords", "embedding_search")

        # 웹: 배치 처리 + 리랭킹 통합 노드
        workflow.add_edge("web_search", "process_and_rerank_web")

        # 임베딩: 리랭킹
        workflow.add_edge("embedding_search", "rerank_embedding")

        # 양쪽 결과 병합
        workflow.add_edge("process_and_rerank_web", "merge_results")
        workflow.add_edge("rerank_embedding", "merge_results")

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
        return {"keywords": keywords}
    
    async def _web_search(self, state: PoiAgentState) -> dict:
        """웹 검색 노드"""
        keywords = state.get("keywords", [])
        if not keywords:
            return {"web_results": []}

        travel_destination = state.get("travel_destination", "")
        results = await self.web_search.search_multiple(
            keywords[:self.keyword_k],
            destination=travel_destination
        )

        for result in results:
            logger.info(f"웹 검색 결과: {result.title}")

        return {"web_results": results}

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
        TARGET_COUNT = 20

        all_reranked: List[PoiSearchResult] = []
        all_poi_data: Dict[str, PoiData] = {}
        semaphore = asyncio.Semaphore(5)

        for batch_start in range(0, len(web_results), BATCH_SIZE):
            batch = web_results[batch_start:batch_start + BATCH_SIZE]
            logger.info(f"배치 처리 시작: {batch_start + 1}~{batch_start + len(batch)} / {len(web_results)}")

            # --- 1) 배치 내 개별 POI 처리 ---
            processed_batch: List[PoiSearchResult] = []
            batch_poi_data: List[PoiData] = []

            async def process_single_poi(poi_result: PoiSearchResult) -> Optional[PoiSearchResult]:
                async with semaphore:
                    try:
                        poi_info = await self.info_summarizer.summarize_single(
                            poi_result=poi_result,
                            persona_summary=persona_summary
                        )
                        if not poi_info:
                            logger.warning(f"POI 요약 실패 (summarize_single): {poi_result}")
                            return None

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
                            return None

                        if not poi_data:
                            return None

                        batch_poi_data.append(poi_data)
                        return PoiSearchResult(
                            poi_id=poi_data.id,
                            title=poi_result.title,
                            snippet=poi_result.snippet,
                            url=poi_result.url,
                            source=poi_result.source,
                            relevance_score=poi_result.relevance_score
                        )
                    except Exception as e:
                        logger.error(f"POI 처리 중 오류: {poi_result.title} - {e}")
                        return None

            tasks = [process_single_poi(r) for r in batch]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            for result in results:
                if isinstance(result, PoiSearchResult):
                    processed_batch.append(result)
                elif isinstance(result, Exception):
                    logger.error(f"POI 처리 예외: {result}")

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
                reranked_batch = await self.reranker.rerank(processed_batch, persona_summary)
                all_reranked.extend(reranked_batch)

            # --- 3) 조기 종료 검사 ---
            good_count = sum(1 for r in all_reranked if r.relevance_score >= MIN_SCORE)
            logger.info(f"배치 완료: 누적 {len(all_reranked)}개, 양호(>={MIN_SCORE}) {good_count}개")

            if good_count >= TARGET_COUNT:
                logger.info(f"목표 달성 ({good_count}>={TARGET_COUNT}), 조기 종료")
                break

        all_reranked.sort(key=lambda x: x.relevance_score, reverse=True)
        logger.info(f"웹 결과 처리+리랭킹 완료: {len(all_reranked)}개 (전체 {len(web_results)}개 중)")
        return {"reranked_web_results": all_reranked, "poi_data_map": all_poi_data}

    async def _embedding_search(self, state: PoiAgentState) -> dict:
        """임베딩 검색 노드

        travel_destination이 있으면 해당 도시로 필터링하여 검색.
        metadata에서 PoiData를 복원하여 poi_data_map에 추가.
        """
        keywords = state.get("keywords", [])
        travel_destination = state.get("travel_destination", "")

        all_pairs: list = []
        for keyword in keywords[:self.keyword_k]:
            pairs = await self.vector_search.search_by_text_with_data(
                query=keyword,
                k=self.embedding_k,
                city_filter=travel_destination
            )
            all_pairs.extend(pairs)

        # 중복 제거
        seen_ids: set = set()
        unique_results: List[PoiSearchResult] = []
        embedding_poi_data_map: Dict[str, PoiData] = {}
        for search_result, poi_data in all_pairs:
            if search_result.poi_id and search_result.poi_id not in seen_ids:
                seen_ids.add(search_result.poi_id)
                unique_results.append(search_result)
                embedding_poi_data_map[search_result.poi_id] = poi_data

        return {
            "embedding_results": unique_results,
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
            embedding_results=emb_reranked
        )
        logger.info(f"merge 출력 (중복 제거 후): {len(merged)}개")

        # 최종 POI 개수 제한
        # merged = merged[:self.final_poi_count]

        # poi_data_map에서 PoiData 조회하여 최종 리스트 생성
        poi_data_map = state.get("poi_data_map", {})
        final_poi_data: List[PoiData] = []

        for result in merged:
            if result.poi_id and result.poi_id in poi_data_map:
                final_poi_data.append(poi_data_map[result.poi_id])
            else:
                logger.warning(f"PoiData not found for poi_id: {result.poi_id}, title: {result.title}")
        logger.info(f"최종 POI 데이터: {final_poi_data}")
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
        POI 검색 워크플로우 실행

        New Flow:
        1. 키워드 추출
        2. 웹 검색 + 임베딩 검색 (병렬)
        3. 웹 결과는 개별 처리되어 VectorDB에 저장됨
        4. 양쪽 결과 리랭킹 후 병합
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
            "final_poi_count": self.final_poi_count
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
            
            print(f"JSON 저장 성공: {file_path}")
            return True
            
        except Exception as e:
            print(f"JSON 저장 실패: {e}")
            return False
