from typing import List, Optional, Any
import json
from datetime import datetime
from pathlib import Path
from langgraph.graph import StateGraph, END
from app.core.models.PoiAgentDataclass.poi import (
    PoiAgentState,
    PoiSearchResult,
    PoiInfo,
    _convert_poi_info_to_data
)
from app.core.LLMClient.BaseLlmClient import BaseLLMClient
from app.core.Agents.Poi.QueryExtention.QueryExtention import QueryExtension
from app.core.Agents.Poi.WebSearch.WebSearchAgent import WebSearchAgent
from app.core.Agents.Poi.VectorDB.VectorSearchAgent import VectorSearchAgent
from app.core.Agents.Poi.ResultMerger import ResultMerger
from app.core.Agents.Poi.InfoSummaizeAgent import InfoSummarizeAgent
from app.core.Agents.Poi.VectorDB.EmbeddingPipeline.EmbeddingPipeline import EmbeddingPipeline
from app.core.Agents.Poi.Reranker.Reranker import Reranker


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
        web_search_api_key: Optional[str] = None,
        vector_db_path: Optional[str] = None,
        web_weight: float = 0.6,
        embedding_weight: float = 0.4,
        rerank_top_n: int = 10
    ):
        # 컴포넌트 초기화
        self.keyword_extractor = QueryExtension(llm_client)
        self.web_search = WebSearchAgent(api_key=web_search_api_key)
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
        
        # 그래프 빌드
        self.graph = self._build_graph()
    
    def _build_graph(self):
        """LangGraph 워크플로우 빌드"""
        workflow = StateGraph(PoiAgentState)
        
        # 노드 추가
        workflow.add_node("extract_keywords", self._extract_keywords)
        workflow.add_node("web_search", self._web_search)
        # workflow.add_node("embedding_search", self._embedding_search)
        workflow.add_node("rerank_web", self._rerank_web)
        # workflow.add_node("rerank_embedding", self._rerank_embedding)
        workflow.add_node("merge_results", self._merge_results)
        workflow.add_node("summarize", self._summarize)
        workflow.add_node("collect_and_store", self._collect_and_store)
        
        # 엔트리 포인트
        workflow.set_entry_point("extract_keywords")
        
        # 엣지 연결
        workflow.add_edge("extract_keywords", "web_search")
        workflow.add_edge("web_search", "rerank_web")
        # workflow.add_edge("rerank_web", "embedding_search")
        # workflow.add_edge("embedding_search", "rerank_embedding")
        workflow.add_edge("rerank_web", "merge_results")
        workflow.add_edge("merge_results", "summarize")
        workflow.add_edge("summarize", "collect_and_store")
        workflow.add_edge("collect_and_store", END)
                
        return workflow.compile()
    
    async def _extract_keywords(self, state: PoiAgentState) -> dict:
        """페르소나에서 키워드 추출 노드"""
        keywords = await self.keyword_extractor.extract_keywords(
            persona_summary=state["persona_summary"]
        )
        return {"keywords": keywords}
    
    async def _web_search(self, state: PoiAgentState) -> dict:
        """웹 검색 노드"""
        keywords = state.get("keywords", [])
        if not keywords:
            return {"web_results": []}
        
        results = await self.web_search.search_multiple(keywords)
        return {"web_results": results}
    
    async def _embedding_search(self, state: PoiAgentState) -> dict:
        """임베딩 검색 노드
        
        travel_destination이 있으면 해당 도시로 필터링하여 검색
        """
        keywords = state.get("keywords", [])
        travel_destination = state.get("travel_destination", "")
        
        all_results: List[PoiSearchResult] = []
        for keyword in keywords[:5]:  # 상위 5개 키워드 사용
            results = await self.vector_search.search_by_text(
                query=keyword, 
                k=5,
                city_filter=travel_destination if travel_destination else None
            )
            all_results.extend(results)
        
        # 중복 제거
        seen_ids = set()
        unique_results = []
        for result in all_results:
            if result.poi_id and result.poi_id not in seen_ids:
                seen_ids.add(result.poi_id)
                unique_results.append(result)
        
        return {"embedding_results": unique_results}
    
    async def _rerank_web(self, state: PoiAgentState) -> dict:
        """웹 검색 결과 리랭킹 노드"""
        web_results = state.get("web_results", [])
        persona_summary = state["persona_summary"]
        
        reranked = await self.reranker.rerank(web_results, persona_summary)
        return {"reranked_web_results": reranked}
    
    async def _rerank_embedding(self, state: PoiAgentState) -> dict:
        """임베딩 검색 결과 리랭킹 노드"""
        embedding_results = state.get("embedding_results", [])
        persona_summary = state["persona_summary"]
        
        reranked = await self.reranker.rerank(embedding_results, persona_summary)
        return {"reranked_embedding_results": reranked}
    
    async def _merge_results(self, state: PoiAgentState) -> dict:
        """결과 병합 노드 (리랭킹된 결과 사용)"""
        merged = self.result_merger.merge(
            web_results=state.get("reranked_web_results", []),
            embedding_results=state.get("reranked_embedding_results", [])
        )
        return {"merged_results": merged}
    
    async def _summarize(self, state: PoiAgentState) -> dict:
        """정보 요약 노드"""
        pois = await self.info_summarizer.summarize(
            merged_results=state.get("merged_results", []),
            persona_summary=state["persona_summary"]
        )
        return {"final_pois": pois}
    
    async def _collect_and_store(self, state: PoiAgentState) -> dict:
        """
        final_pois를 PoiData로 변환하여 VectorDB에 저장
        InfoSummarizeAgent의 결과를 재사용하여 PoiCollector 역할 통합
        """
        final_pois = state.get("final_pois", [])
        travel_destination = state.get("travel_destination", "")
        
        if final_pois:
            # PoiInfo -> PoiData 변환
            poi_data_list = [
                _convert_poi_info_to_data(poi, travel_destination)
                for poi in final_pois
            ]
            
            # VectorDB에 저장
            await self.vector_search.add_pois_batch(poi_data_list)
        
        return {}
    
    async def run(
        self, 
        persona_summary: str, 
        travel_destination: str,
        save_path: Optional[str] = None
    ) -> List[PoiInfo]:
        """
        POI 검색 워크플로우 실행
        
        Args:
            persona_summary: 사용자 페르소나 요약
            travel_destination: 사용자가 여행하는 지역
            save_path: JSON 저장 경로 (선택적)
            
        Returns:
            추천 POI 목록
        """
        initial_state: PoiAgentState = {
            "travel_destination": travel_destination,
            "persona_summary": persona_summary,
            "keywords": [],
            "web_results": [],
            "embedding_results": [],
            "reranked_web_results": [],
            "reranked_embedding_results": [],
            "merged_results": [],
            "final_pois": []
        }
        
        result = await self.graph.ainvoke(initial_state)
        
        # JSON 저장 (요청 시)
        if save_path:
            self.save_state_to_json(result, save_path)
        
        return result.get("final_pois", [])
    
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
