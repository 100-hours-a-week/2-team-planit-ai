from app.core.LLMClient.OpenAiApiClient import OpenAiApiClient
from app.core.config import settings

openai_client = OpenAiApiClient(api_key=settings.openai_api_key)

print(openai_client.call_llm("Hello, how are you?"))

async def test_stream():
    async for chunk in openai_client.call_llm_stream("Hello, how are you?"):
        print(chunk, end="\n", flush=True)

if __name__ == "__main__":
    import asyncio
    asyncio.run(test_stream())
