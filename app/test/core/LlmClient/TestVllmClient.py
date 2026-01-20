from app.core.LLMClient.VllmClient import VllmClient

vllm_client = VllmClient()

print("================= call_llm =================")
print(vllm_client.call_llm("Hello, how are you?"))

print("================= call_llm_stream =================")
async def test_stream():
    async for chunk in vllm_client.call_llm_stream("Hello, how are you?"):
        print(chunk, end="\n", flush=True)

if __name__ == "__main__":
    import asyncio
    asyncio.run(test_stream())
