import pytest
from pydantic import BaseModel
from app.core.LLMClient.VllmClient import VllmClient
from app.core.models.LlmClientDataclass.ChatMessageDataclass import ChatMessage, MessageData

# --- Test Models ---
class SimpleResponse(BaseModel):
    answer: str
    confidence: int

# --- Fixtures ---
@pytest.fixture
def client():
    return VllmClient()

@pytest.fixture
def chat_message():
    return ChatMessage(
        content=[
            MessageData(role="user", content="Hello, are you working?")
        ]
    )

# --- Unit Tests (Accuracy Verification) ---
class TestVllmClientUnit:
    """
    call_llm이 아닌 함수들은 정확한 값이 나오는지 확인
    """
    
    def test_message_data_to_dict(self, client):
        msg_data = MessageData(role="user", content="Hello")
        expected = {"role": "user", "content": "Hello"}
        assert client.messageDataToDict(msg_data) == expected

    def test_dict_to_message_data(self, client):
        data = {"role": "assistant", "content": "Hi"}
        result = client.dictToMessageData(data)
        assert isinstance(result, MessageData)
        assert result.role == "assistant"
        assert result.content == "Hi"

    def test_chat_message_to_dict_list(self, client):
        chat_msg = ChatMessage(
            content=[
                MessageData(role="user", content="Hello"),
                MessageData(role="assistant", content="Hi")
            ]
        )
        expected = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi"}
        ]
        assert client.chatMessageToDictList(chat_msg) == expected

    def test_dict_list_to_chat_message(self, client):
        data_list = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi"}
        ]
        result = client.dictListToChatMessage(data_list)
        assert isinstance(result, ChatMessage)
        assert len(result.content) == 2
        assert result.content[0].role == "user"
        assert result.content[0].content == "Hello"
        assert result.content[1].role == "assistant"
        assert result.content[1].content == "Hi"

# --- Integration Tests (Existence Verification) ---
class TestVllmClientIntegration:
    """
    call_llm 관련 함수들은 실행 결과가 실제로 나오는지만 확인
    (Note: 실제 vLLM 서버가 연결되어 있어야 성공함)
    """

    def test_call_llm(self, client, chat_message):
        """call_llm 실행 및 결과 반환 확인"""
        import asyncio
        async def run():
            result = await client.call_llm(chat_message)
            print(f"\n[call_llm] Result: {result}")
            return result

        try:
            result = asyncio.run(run())
            # 결과가 문자열이고 비어있지 않은지 확인
            assert isinstance(result, str)
            assert len(result) > 0
            assert "LLM 서버 오류" not in result
            assert "LLM 서버 요청 실패" not in result
        except Exception as e:
            pytest.fail(f"call_llm execution failed: {e}")

    def test_call_llm_stream(self, client, chat_message):
        """call_llm_stream 실행 및 스트리밍 결과 반환 확인"""
        import asyncio
        async def run():
            full_content = ""
            async for chunk in client.call_llm_stream(chat_message):
                assert isinstance(chunk, str)
                full_content += chunk
            return full_content

        try:
            full_content = asyncio.run(run())
            print(f"\n[call_llm_stream] Result: {full_content}")
            
            # 전체 스트리밍 결과가 존재하는지 확인
            assert len(full_content) > 0
            assert "LLM 서버 오류" not in full_content
            assert "LLM 서버 요청 실패" not in full_content
        except Exception as e:
            pytest.fail(f"call_llm_stream execution failed: {e}")

    def test_call_llm_structured(self, client):
        """call_llm_structured 실행 및 Pydantic 모델 반환 확인"""
        import asyncio
        async def run():
            prompt = ChatMessage(
                content=[
                    MessageData(role="user", content="Generate a sample JSON with answer='Test Success' and confidence=99.")
                ]
            )
            return await client.call_llm_structured(prompt, SimpleResponse)

        try:
            result = asyncio.run(run())
            print(f"\n[call_llm_structured] Result: {result}")
            
            # 결과가 SimpleResponse 타입인지 확인
            assert isinstance(result, SimpleResponse)
            assert isinstance(result.answer, str)
            assert isinstance(result.confidence, int)
            
        except Exception as e:
            # 서버 연결 실패 등의 이유로 실패할 수 있음. 
            # 단순히 결과가 나오는지 확인하는 것이 목적이므로, 에러 발생 시 출력하고 fail 처리
            pytest.fail(f"call_llm_structured failed: {e}")
