from __future__ import annotations

import os

from dotenv import load_dotenv

# Load the project-root .env regardless of the current working directory,
# so exercises run correctly from any section folder. Root is the parent
# of the `shared/` package this file lives in.
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(_PROJECT_ROOT, ".env"))


# --------------------------------------------------------------------------- #
# Settings
# --------------------------------------------------------------------------- #
class Settings:
    """Static configuration shared across every exercise."""

    def __init__(self) -> None:
        # The Gemini model to use. Swap freely while experimenting.
        #   - models/gemini-2.0-flash : fast, free-tier available
        #   - models/gemini-2.5-pro   : stronger reasoning, paid only
        self.model: str = os.getenv("GEMINI_MODEL", "models/gemini-2.0-flash")

        # API key is read from the environment; kept out of source control.
        self.api_key: str = os.getenv("GEMINI_API_KEY", "")

        # Default sampling parameters. Individual exercises override these
        # (e.g. exercise 2 sweeps temperature explicitly).
        self.temperature: float = float(os.getenv("GEMINI_TEMPERATURE", "0.7"))
        self.top_p: float = float(os.getenv("GEMINI_TOP_P", "0.95"))
        self.top_k: int = int(os.getenv("GEMINI_TOP_K", "40"))
        self.max_output_tokens: int = int(os.getenv("GEMINI_MAX_OUTPUT_TOKENS", "1024"))

        # Optional fixed seed for reproducible runs. None (default) = stochastic;
        # set GEMINI_SEED to an int to make same input → same output.
        self.seed: int | None = (
            int(os.environ["GEMINI_SEED"]) if os.getenv("GEMINI_SEED") else None
        )

    def require_api_key(self) -> str:
        """Return the API key or raise a clear error if it is missing."""
        if not self.api_key:
            raise RuntimeError(
                "GEMINI_API_KEY is not set. Copy .env.example to .env and add "
                "your key (get one at https://aistudio.google.com/apikey)."
            )
        return self.api_key


SETTINGS = Settings()


# --------------------------------------------------------------------------- #
# Provider-agnostic LLM factory
# --------------------------------------------------------------------------- #
# All agent modules call get_llm() to obtain a BaseChatModel.
# To switch providers, change only this function — every module inherits the swap.
#
# Example — switch to OpenAI:
#   from langchain_openai import ChatOpenAI
#   return ChatOpenAI(model="gpt-4o", temperature=temperature, max_tokens=max_tokens)
#
# Example — switch to Anthropic:
#   from langchain_anthropic import ChatAnthropic
#   return ChatAnthropic(model="claude-opus-4-6", temperature=temperature, max_tokens=max_tokens)
def get_llm(temperature: float = 0.3, max_tokens: int = 1024):
    """Return a provider-agnostic LangChain chat model (default: Gemini)."""
    from langchain_google_genai import ChatGoogleGenerativeAI  # lazy import

    return ChatGoogleGenerativeAI(
        model=SETTINGS.model,
        google_api_key=SETTINGS.require_api_key(),
        temperature=temperature,
        max_output_tokens=max_tokens,
    )


def get_embedder():
    """Return a provider-agnostic LangChain embeddings model (default: Gemini text-embedding-004)."""
    from langchain_google_genai import GoogleGenerativeAIEmbeddings  # lazy import

    return GoogleGenerativeAIEmbeddings(
        model="models/text-embedding-004",
        google_api_key=SETTINGS.require_api_key(),
    )
