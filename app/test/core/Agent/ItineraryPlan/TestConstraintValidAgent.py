"""
ConstraintValidAgent 테스트
"""
import pytest
from app.core.Agents.ItineraryPlan.ConstraintValidAgent import ConstraintValidAgent
from app.core.models.ItineraryAgentDataclass.itinerary import Itinerary
from app.core.models.PoiAgentDataclass.poi import PoiData, PoiCategory, PoiSource


class TestConstraintValidAgent:
    """ConstraintValidAgent 테스트"""

    @pytest.fixture
    def agent(self):
        """기본 에이전트"""
        return ConstraintValidAgent()

    @pytest.fixture
    def sample_pois(self):
        """테스트용 POI 리스트"""
        return [
            PoiData(
                id=f"poi_{i}",
                name=f"장소 {i}",
                category=PoiCategory.ATTRACTION,
                source=PoiSource.WEB_SEARCH,
                raw_text=f"테스트 장소 {i}"
            )
            for i in range(4)
        ]

    @pytest.fixture
    def valid_itinerary(self, sample_pois):
        """유효한 일정"""
        return Itinerary(
            date="2024-01-15",
            pois=sample_pois,
            transfers=[],
            total_duration_minutes=300  # 5시간
        )

    @pytest.fixture
    def overtime_itinerary(self, sample_pois):
        """시간 초과 일정"""
        return Itinerary(
            date="2024-01-15",
            pois=sample_pois,
            transfers=[],
            total_duration_minutes=800  # 13시간 (기본 12시간 초과)
        )

    # === 예산 검증 테스트 ===

    def test_validate_budget_within_limit(self, agent, valid_itinerary):
        """예산 내 일정"""
        result = agent.validate(
            itineraries=[valid_itinerary],
            total_budget=500000,  # 50만원
            travel_start_date="2024-01-15",
            travel_end_date="2024-01-15"
        )
        # POI 4개 * 30000 = 120000 < 500000
        assert result is None

    def test_validate_budget_over_limit(self, agent, sample_pois):
        """예산 초과 일정"""
        # POI 10개 생성
        many_pois = [
            PoiData(
                id=f"poi_{i}",
                name=f"장소 {i}",
                category=PoiCategory.ATTRACTION,
                source=PoiSource.WEB_SEARCH,
                raw_text=f"테스트 {i}"
            )
            for i in range(10)
        ]
        itinerary = Itinerary(
            date="2024-01-15",
            pois=many_pois,
            total_duration_minutes=300
        )

        result = agent.validate(
            itineraries=[itinerary],
            total_budget=100000,  # 10만원
            travel_start_date="2024-01-15",
            travel_end_date="2024-01-15"
        )
        # POI 10개 * 30000 = 300000 > 100000
        assert result is not None
        assert "예산 초과" in result

    # === 시간 검증 테스트 ===

    def test_validate_time_within_limit(self, agent, valid_itinerary):
        """시간 내 일정"""
        result = agent._validate_daily_time([valid_itinerary])
        assert result is None

    def test_validate_time_over_limit(self, agent, overtime_itinerary):
        """시간 초과 일정"""
        result = agent._validate_daily_time([overtime_itinerary])
        assert result is not None
        assert "시간 초과" in result

    # === 날짜 검증 테스트 ===

    def test_validate_date_range_valid(self, agent, valid_itinerary):
        """유효한 날짜 범위"""
        result = agent._validate_date_range(
            [valid_itinerary],
            travel_start_date="2024-01-15",
            travel_end_date="2024-01-15"
        )
        assert result is None

    def test_validate_date_range_before_start(self, agent):
        """시작일보다 앞선 일정"""
        itinerary = Itinerary(
            date="2024-01-14",  # 시작일보다 하루 전
            pois=[],
            total_duration_minutes=0
        )

        result = agent._validate_date_range(
            [itinerary],
            travel_start_date="2024-01-15",
            travel_end_date="2024-01-17"
        )
        assert result is not None
        assert "날짜 범위 오류" in result

    def test_validate_empty_itineraries(self, agent):
        """빈 일정"""
        result = agent._validate_date_range(
            [],
            travel_start_date="2024-01-15",
            travel_end_date="2024-01-17"
        )
        assert result is not None
        assert "일정 없음" in result


class TestScheduleAgent:
    """ScheduleAgent 테스트"""

    @pytest.fixture
    def agent(self):
        """기본 에이전트"""
        from app.core.Agents.ItineraryPlan.ScheduleAgent import ScheduleAgent
        return ScheduleAgent()

    @pytest.fixture
    def sample_pois(self, count=4):
        """테스트용 POI 리스트"""
        return [
            PoiData(
                id=f"poi_{i}",
                name=f"장소 {i}",
                category=PoiCategory.ATTRACTION,
                source=PoiSource.WEB_SEARCH,
                raw_text=f"테스트 {i}"
            )
            for i in range(count)
        ]

    def test_analyze_balanced_schedule(self, agent, sample_pois):
        """균형 잡힌 일정"""
        itinerary = Itinerary(
            date="2024-01-15",
            pois=sample_pois,  # 4개 (optimal)
            total_duration_minutes=300
        )

        result = agent.analyze([itinerary])
        assert result is None

    def test_analyze_overloaded_day(self, agent):
        """과부하 일정"""
        many_pois = [
            PoiData(
                id=f"poi_{i}",
                name=f"장소 {i}",
                category=PoiCategory.ATTRACTION,
                source=PoiSource.WEB_SEARCH,
                raw_text=f"테스트 {i}"
            )
            for i in range(8)  # max 6개 초과
        ]
        itinerary = Itinerary(
            date="2024-01-15",
            pois=many_pois,
            total_duration_minutes=600
        )

        result = agent.analyze([itinerary])
        assert result is not None
        assert "과다" in result

    def test_analyze_empty_day(self, agent):
        """빈 일정"""
        itinerary = Itinerary(
            date="2024-01-15",
            pois=[],
            total_duration_minutes=0
        )

        result = agent.analyze([itinerary])
        assert result is not None
        assert "빈 일정" in result


class TestTodoAgent:
    """TodoAgent 테스트"""

    @pytest.fixture
    def agent(self):
        """기본 에이전트"""
        from app.core.Agents.ItineraryPlan.TodoAgent import TodoAgent
        return TodoAgent()

    def test_plan_tasks_with_poi_changed(self, agent):
        """POI 변경 시 Task Queue"""
        state = {
            "is_poi_changed": True,
            "validation_feedback": None,
            "schedule_feedback": None
        }

        tasks = agent.plan_tasks(state)

        assert "DistanceCalculateAgent" in tasks
        assert "ConstraintValidAgent" in tasks
        assert "ScheduleAgent" in tasks

    def test_plan_tasks_without_poi_changed(self, agent):
        """POI 변경 없을 시 Task Queue"""
        state = {
            "is_poi_changed": False,
            "validation_feedback": None,
            "schedule_feedback": None
        }

        tasks = agent.plan_tasks(state)

        # POI 변경 없으면 DistanceCalculateAgent 제외
        assert "DistanceCalculateAgent" not in tasks
        assert "ConstraintValidAgent" in tasks

    def test_plan_tasks_with_feedback(self, agent):
        """피드백 있을 시 Task Queue"""
        state = {
            "is_poi_changed": False,
            "validation_feedback": "예산 초과",
            "schedule_feedback": None
        }

        tasks = agent.plan_tasks(state)

        # 피드백 있으면 ItineraryPlanAgent부터 시작
        assert tasks[0] == "ItineraryPlanAgent"

    def test_get_next_task(self, agent):
        """다음 태스크 가져오기"""
        state = {
            "task_queue": ["DistanceCalculateAgent", "ConstraintValidAgent"]
        }

        next_task = agent.get_next_task(state)
        assert next_task == "DistanceCalculateAgent"

    def test_get_next_task_empty_queue(self, agent):
        """빈 큐에서 다음 태스크"""
        state = {"task_queue": []}

        next_task = agent.get_next_task(state)
        assert next_task is None

    def test_is_complete(self, agent):
        """완료 여부 확인"""
        assert agent.is_complete({"task_queue": []}) is True
        assert agent.is_complete({"task_queue": ["task1"]}) is False

    def test_check_poi_changed(self, agent):
        """POI 변경 감지"""
        assert agent.check_poi_changed(["a", "b"], ["a", "b"]) is False
        assert agent.check_poi_changed(["a", "b", "c"], ["a", "b"]) is True
        assert agent.check_poi_changed(["a", "c"], ["a", "b"]) is True
