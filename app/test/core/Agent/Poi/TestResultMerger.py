import pytest
from app.core.Agents.Poi.ResultMerger import ResultMerger
from app.core.models.PoiAgentDataclass.poi import PoiSearchResult, PoiSource


class TestResultMerger:
    """ResultMerger 테스트"""
    
    @pytest.fixture
    def merger(self):
        """기본 가중치로 ResultMerger 생성"""
        return ResultMerger(web_weight=0.6, embedding_weight=0.4)
    
    @pytest.fixture
    def web_results(self):
        """웹 검색 결과 샘플"""
        return [
            PoiSearchResult(
                title="웹 결과 1",
                snippet="웹 검색 결과 1번",
                url="https://example.com/1",
                source=PoiSource.WEB_SEARCH,
                relevance_score=0.9
            ),
            PoiSearchResult(
                title="웹 결과 2",
                snippet="웹 검색 결과 2번",
                url="https://example.com/2",
                source=PoiSource.WEB_SEARCH,
                relevance_score=0.8
            )
        ]
    
    @pytest.fixture
    def embedding_results(self):
        """임베딩 검색 결과 샘플"""
        return [
            PoiSearchResult(
                poi_id="poi-1",
                title="임베딩 결과 1",
                snippet="임베딩 검색 결과 1번",
                source=PoiSource.EMBEDDING_DB,
                relevance_score=0.85
            ),
            PoiSearchResult(
                poi_id="poi-2",
                title="임베딩 결과 2",
                snippet="임베딩 검색 결과 2번",
                source=PoiSource.EMBEDDING_DB,
                relevance_score=0.75
            )
        ]
    
    def test_merge_applies_weights(self, merger, web_results, embedding_results):
        """가중치 적용 테스트"""
        merged = merger.merge(web_results, embedding_results)
        
        # 결과가 반환되어야 함
        assert len(merged) > 0
        
        # 모든 결과가 PoiSearchResult 타입이어야 함
        for result in merged:
            assert isinstance(result, PoiSearchResult)
    
    def test_merge_removes_duplicates_by_url(self, merger):
        """URL 기반 중복 제거 테스트"""
        web_results = [
            PoiSearchResult(
                title="중복 결과",
                snippet="동일 URL",
                url="https://example.com/same",
                source=PoiSource.WEB_SEARCH,
                relevance_score=0.8
            )
        ]
        embedding_results = [
            PoiSearchResult(
                poi_id="poi-same",
                title="중복 결과",
                snippet="동일 URL",
                url="https://example.com/same",
                source=PoiSource.EMBEDDING_DB,
                relevance_score=0.7
            )
        ]
        
        merged = merger.merge(web_results, embedding_results)
        
        # 중복 제거되어 1개만 남아야 함
        assert len(merged) == 1
        # 점수가 합산되어야 함 (0.8 * 0.6 + 0.7 * 0.4 = 0.76)
        assert merged[0].relevance_score == pytest.approx(0.76, rel=0.01)
    
    def test_merge_sorts_by_score(self, merger, web_results, embedding_results):
        """점수순 정렬 테스트"""
        merged = merger.merge(web_results, embedding_results)
        
        # 점수가 높은 순으로 정렬되어야 함
        for i in range(len(merged) - 1):
            assert merged[i].relevance_score >= merged[i + 1].relevance_score
    
    def test_merge_respects_max_results(self, merger):
        """최대 결과 수 제한 테스트"""
        web_results = [
            PoiSearchResult(
                title=f"결과 {i}",
                snippet=f"내용 {i}",
                url=f"https://example.com/{i}",
                source=PoiSource.WEB_SEARCH,
                relevance_score=0.9 - i * 0.1
            )
            for i in range(10)
        ]
        
        merged = merger.merge(web_results, [], max_results=5)
        
        assert len(merged) == 5
    
    def test_merge_handles_empty_web_results(self, merger, embedding_results):
        """웹 결과 비어있을 때 테스트"""
        merged = merger.merge([], embedding_results)
        
        assert len(merged) == 2
    
    def test_merge_handles_empty_embedding_results(self, merger, web_results):
        """임베딩 결과 비어있을 때 테스트"""
        merged = merger.merge(web_results, [])
        
        assert len(merged) == 2
    
    def test_merge_handles_both_empty(self, merger):
        """둘 다 비어있을 때 테스트"""
        merged = merger.merge([], [])
        
        assert len(merged) == 0
    
    def test_get_result_key_with_url(self, merger):
        """URL 기반 키 생성 테스트"""
        result = PoiSearchResult(
            title="테스트",
            snippet="내용",
            url="https://example.com/test",
            source=PoiSource.WEB_SEARCH
        )
        
        key = merger._get_result_key(result)
        assert key == "https://example.com/test"
    
    def test_get_result_key_with_poi_id(self, merger):
        """POI ID 기반 키 생성 테스트"""
        result = PoiSearchResult(
            poi_id="poi-123",
            title="테스트",
            snippet="내용",
            source=PoiSource.EMBEDDING_DB
        )
        
        key = merger._get_result_key(result)
        assert key == "poi:poi-123"
    
    def test_get_result_key_with_title_only(self, merger):
        """제목 기반 키 생성 테스트"""
        result = PoiSearchResult(
            title="테스트 제목",
            snippet="내용",
            source=PoiSource.WEB_SEARCH
        )
        
        key = merger._get_result_key(result)
        assert key == "title:테스트 제목"
