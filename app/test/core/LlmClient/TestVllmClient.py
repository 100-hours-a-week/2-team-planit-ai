from app.core.LLMClient.VllmClient import VllmClient

vllm_client = VllmClient()

async def test_stream():
    async for chunk in vllm_client.call_llm_stream("Hello, how are you?"):
        print(chunk, end="", flush=True)


if __name__ == "__main__":
    import asyncio
    print("================= call_llm_stream =================")
    asyncio.run(test_stream())
    print()

    print("================= call_llm =================")
    print(vllm_client.call_llm("Hello, how are you?"))
