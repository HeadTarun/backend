"""LLM verification test — tests configured LiteLLM AI Gateway providers (Groq, Gemini, Ollama, HuggingFace)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from langchain_core.messages import HumanMessage
from product_agent.config import get_settings
from product_agent.llm import build_gateway_chat_model


def main() -> None:
    settings = get_settings()
    print("=" * 70)
    print("🤖 TESTING CONFIGURED LLM PROVIDERS & AI GATEWAY")
    print("=" * 70)

    print(f"Groq Key Present:   {'YES' if settings.groq_api_key else 'NO'}")
    print(f"Gemini Key Present: {'YES' if settings.gemini_api_key else 'NO'}")
    print(f"HF Token Present:   {'YES' if settings.hf_token else 'NO'}")
    print(f"Gateway Model:      {settings.gateway_model or 'Auto-selected'}")

    model = build_gateway_chat_model(settings)
    print(f"\nPrimary Model:     {model.model}")
    print(f"Fallback Models:   {model.fallback_models}")

    print("\nSending test prompt to AI Gateway...")
    test_messages = [
        HumanMessage(content="Respond with exact valid JSON: {\"status\": \"ok\", \"message\": \"LLM gateway operational\"}")
    ]

    try:
        res = model.invoke(test_messages)
        print("\n✅ SUCCESS! LLM Response received:")
        print("-" * 50)
        print(res.content)
        print("-" * 50)
    except Exception as exc:
        print("\n❌ LLM Gateway Failed:")
        print(exc)
        sys.exit(1)


if __name__ == "__main__":
    main()
