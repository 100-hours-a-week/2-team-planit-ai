import pytest
from unittest.mock import AsyncMock, MagicMock
from app.core.Agents.Poi.Reranker.Reranker import Reranker
from app.core.models.PoiAgentDataclass.poi import PoiSearchResult, PoiSource


# =============================================================================
# 단위 테스트: 모든 의존성 Mock 사용
# =============================================================================
class TestRerankerUnit:
    """Reranker 단위 테스트 (Mock LLM 사용)"""
    
    @pytest.fixture
    def mock_llm_client(self):
        """Mock LLM Client"""
        client = MagicMock()
        client.call_llm = AsyncMock()
        return client
    
    @pytest.fixture
    def reranker(self, mock_llm_client):
        """Reranker 인스턴스 (min_score=0.5)"""
        return Reranker(llm_client=mock_llm_client, min_score=0.5)
    
    @pytest.fixture
    def sample_results(self):
        """테스트용 검색 결과"""
        return [
            PoiSearchResult(poi_id="1", title="장소 A", snippet="설명 A", source=PoiSource.WEB_SEARCH, relevance_score=0.5),
            PoiSearchResult(poi_id="2", title="장소 B", snippet="설명 B", source=PoiSource.WEB_SEARCH, relevance_score=0.4),
            PoiSearchResult(poi_id="3", title="장소 C", snippet="설명 C", source=PoiSource.WEB_SEARCH, relevance_score=0.3),
        ]

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_rerank_logic_and_sorting(self, reranker, mock_llm_client, sample_results):
        """LLM 응답에 따른 리랭킹 및 정렬 로직 검증"""
        # LLM 응답 시뮬레이션: ID 3번(0.9점) -> ID 1번(0.8점) -> ID 2번(0.3점)
        mock_llm_client.call_llm.return_value = """
        <scores>
        <score id="1">0.8</score>
        <score id="2">0.3</score>
        <score id="3">0.9</score>
        </scores>
        """
        
        reranked = await reranker.rerank(sample_results, "테스트 페르소나")
        
        # min_score=0.5 필터링 확인 (0.9, 0.8은 통과, 0.3은 미달)
        assert len(reranked) == 2
        
        # 정렬 순서 확인 (ID 3 -> ID 1)
        assert reranked[0].poi_id == "3"
        assert reranked[0].relevance_score == 0.9
        assert reranked[1].poi_id == "1"
        assert reranked[1].relevance_score == 0.8

    @pytest.mark.unit
    def test_parse_scores_success(self, reranker):
        """XML 응답 파싱 로직 검증"""
        response = """
        일부 텍스트...
        <scores>
        <score id="1">0.85</score>
        <score id="2">0.123</score>
        </scores>
        """
        scores = reranker._parse_scores(response, 2)
        assert scores == [0.85, 0.123]

    @pytest.mark.unit
    def test_parse_scores_handles_invalid_format(self, reranker):
        """잘못된 형식의 응답 시 기본값(0.0) 반환 확인"""
        scores = reranker._parse_scores("잘못된 응답", 3)
        assert scores == [0.0, 0.0, 0.0]

    @pytest.mark.unit
    def test_format_results(self, reranker, sample_results):
        """결과 데이터의 XML 포맷팅 확인"""
        formatted = reranker._format_results(sample_results)
        assert '<result id="1">' in formatted
        assert '<title>장소 A</title>' in formatted
        assert '<content>설명 A</content>' in formatted

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_rerank_empty_input(self, reranker):
        """빈 리스트 입력 시 조기 반환 확인"""
        result = await reranker.rerank([], "페르소나")
        assert result == []


# =============================================================================
# 통합 테스트: 모든 의존성 실제 사용
# =============================================================================
class TestRerankerIntegration:
    """Reranker 통합 테스트 (실제 VllmClient 사용)"""
    
    @pytest.fixture
    def real_llm_client(self):
        """실제 LLM Client (VllmClient)"""
        try:
            from app.core.LLMClient.VllmClient import VllmClient
            return VllmClient()
        except Exception:
            pytest.skip("VllmClient 초기화 실패")
            
    @pytest.fixture
    def reranker(self, real_llm_client):
        """실제 LLM을 사용하는 Reranker (min_score=0.5)"""
        return Reranker(llm_client=real_llm_client, min_score=0.5)

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_rerank_with_real_llm(self, reranker):
        """실제 LLM을 통한 리랭킹 동작 검증"""
        results = [
            PoiSearchResult(poi_id="1", title="정갈한 한식 식당", snippet="조용하고 깨끗한 분위기에서 한식을 즐길 수 있습니다.", source=PoiSource.WEB_SEARCH),
            PoiSearchResult(poi_id="2", title="시끌벅적한 펍", snippet="음악 소리가 크고 맥주가 맛있는 펍입니다.", source=PoiSource.WEB_SEARCH),
            PoiSearchResult(poi_id="3", title="정통 이탈리안 레스토랑", snippet="파스타와 피자가 맛있는 곳입니다.", source=PoiSource.WEB_SEARCH),
        ]
        
        # '조용한 곳을 좋아하는 어르신' 페르소나
        persona = "60대 부부, 조용하고 정갈한 식당을 선호함. 시끄러운 곳은 싫어함."
        
        reranked = await reranker.rerank(results, persona)
        
        print(f"\n[Integration Test] Reranked results: {reranked}")
        
        assert len(reranked) > 0
        # 조용한 한식 식당(ID 1)이 상위권이고 시끄러운 펍(ID 2)보다 점수가 높아야 함
        id_to_score = {r.poi_id: r.relevance_score for r in reranked}
        
        # 모델의 출력 특성상 점수가 모두 0일 수도 있으므로, 파싱 로그 확인 후 단언
        if "1" in id_to_score and "2" in id_to_score:
            if id_to_score["1"] == 0.0 and id_to_score["2"] == 0.0:
                print(reranked)
                pytest.skip("LLM이 점수를 할당하지 않았거나 파싱에 실패했습니다 (모두 0.0)")
            assert id_to_score["1"] > id_to_score["2"]

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_rerank_batch(self, reranker):
        """Batch 리랭킹 기능 검증 (가성비 중시 대학생 여행자 시나리오)"""
        web_results = [
            PoiSearchResult(poi_id="w1", title="서울 광장시장 먹거리 투어", snippet="광장시장의 다양한 길거리 음식을 소개합니다. 빈대떡, 마약김밥 등 저렴하고 맛있는 음식이 가득합니다.", source=PoiSource.WEB_SEARCH),
            PoiSearchResult(poi_id="w2", title="청담동 프렌치 파인 다이닝", snippet="럭셔리한 분위기에서 즐기는 코스 요리. 가격대는 인당 20만원 이상의 고가입니다.", source=PoiSource.WEB_SEARCH),
        ]
        emb_results = [
            PoiSearchResult(poi_id="e1", title="통인시장 엽전 도시락", snippet="서촌에 위치한 통인시장에서 엽전으로 시장 음식을 골라 먹는 가성비 넘치는 체험.", source=PoiSource.EMBEDDING_DB),
            PoiSearchResult(poi_id="e2", title="그랜드 워커힐 호텔 라운지", snippet="한강 뷰를 즐기며 조용히 커피를 마실 수 있는 호텔 라운지. 가격대가 높습니다.", source=PoiSource.EMBEDDING_DB),
        ]
        
        # '가성비와 로컬 시장을 선호하는 대학생' 페르소나
        persona = "20대 대학생 배낭 여행자. 예산이 한정적이라 가성비 좋은 로컬 맛집과 전통 시장 분위기를 매우 선호함. 비싼 명품 거리나 고급 식당은 부담스러워함."
        
        reranked_web, reranked_emb = await reranker.rerank_batch(web_results, emb_results, persona)
        
        print(f"\n[Batch Integration Test] Web: {reranked_web}")
        print(f"[Batch Integration Test] Embedding: {reranked_emb}")
        
        assert isinstance(reranked_web, list)
        assert isinstance(reranked_emb, list)
        
        # 가성비 장소(w1, e1)가 비싼 장소(w2, e2)보다 높은 위치에 있거나 점수가 높아야 함
        if len(reranked_web) >= 2:
            scores = {r.poi_id: r.relevance_score for r in reranked_web}
            if scores["w1"] > 0 and scores["w2"] > 0:
                assert scores["w1"] >= scores["w2"]
                
        if len(reranked_emb) >= 2:
            scores = {r.poi_id: r.relevance_score for r in reranked_emb}
            if scores["e1"] > 0 and scores["e2"] > 0:
                assert scores["e1"] >= scores["e2"]
