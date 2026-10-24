"""Provider-agnostic LLM factory returning LangChain BaseChatModel instances.

Supports OpenAI, Groq, Google Gemini, Anthropic Claude, and Ollama.
"""

from typing import Any
from langchain_core.language_models import BaseChatModel
from tgagent.config import AppConfig


def create_chat_model(config: AppConfig, **kwargs: Any) -> BaseChatModel:
    """Factory returning the primary LangChain chat model based on config.llm.provider.
    
    Used by Supervisor, TaskManager, ChannelMonitor, and Delivery agents.
    """
    provider = (config.llm.provider or "openai").lower()
    model_name = config.llm.control_model
    api_key = config.llm.api_key
    timeout = config.llm.control_timeout_seconds
    temperature = kwargs.pop("temperature", 0.3)

    match provider:
        case "openai":
            from langchain_openai import ChatOpenAI

            base_url = None
            if "openai" in config.llm.providers and config.llm.providers["openai"].base_url:
                base_url = config.llm.providers["openai"].base_url

            return ChatOpenAI(
                model=model_name,
                api_key=api_key,
                base_url=base_url,
                temperature=temperature,
                timeout=timeout,
                max_retries=config.llm.max_retries,
                **kwargs,
            )

        case "groq":
            # Prefer langchain_groq if available, otherwise ChatOpenAI with Groq base URL
            try:
                from langchain_groq import ChatGroq

                return ChatGroq(
                    model=model_name,
                    api_key=api_key,
                    temperature=temperature,
                    timeout=timeout,
                    max_retries=config.llm.max_retries,
                    **kwargs,
                )
            except ImportError:
                from langchain_openai import ChatOpenAI

                return ChatOpenAI(
                    model=model_name,
                    api_key=api_key,
                    base_url="https://api.groq.com/openai/v1",
                    temperature=temperature,
                    timeout=timeout,
                    max_retries=config.llm.max_retries,
                    **kwargs,
                )

        case "gemini":
            from langchain_google_genai import ChatGoogleGenerativeAI

            return ChatGoogleGenerativeAI(
                model=model_name,
                google_api_key=api_key,
                temperature=temperature,
                timeout=timeout,
                max_retries=config.llm.max_retries,
                **kwargs,
            )

        case "anthropic":
            from langchain_anthropic import ChatAnthropic

            return ChatAnthropic(
                model=model_name,
                api_key=api_key,
                temperature=temperature,
                timeout=timeout,
                max_retries=config.llm.max_retries,
                **kwargs,
            )

        case "ollama":
            from langchain_ollama import ChatOllama

            base_url = "http://localhost:11434"
            if "ollama" in config.llm.providers:
                provider_cfg = config.llm.providers["ollama"]
                base_url = provider_cfg.host or provider_cfg.base_url or base_url

            return ChatOllama(
                model=model_name,
                base_url=base_url,
                temperature=temperature,
                **kwargs,
            )

        case _:
            # Fallback to OpenAI-compatible
            from langchain_openai import ChatOpenAI

            return ChatOpenAI(
                model=model_name,
                api_key=api_key,
                temperature=temperature,
                timeout=timeout,
                **kwargs,
            )


def create_classifier_model(config: AppConfig, **kwargs: Any) -> BaseChatModel:
    """Factory returning the classifier LangChain chat model.
    
    Used by PostAnalyst agent for evaluating post relevance.
    Often configured to use a smaller, faster model with near-zero temperature.
    """
    provider = (config.llm.provider or "openai").lower()
    model_name = config.llm.classifier_model
    api_key = config.llm.api_key
    timeout = config.llm.classifier_timeout_seconds
    temperature = kwargs.pop("temperature", 0.0)

    match provider:
        case "openai":
            from langchain_openai import ChatOpenAI

            base_url = None
            if "openai" in config.llm.providers and config.llm.providers["openai"].base_url:
                base_url = config.llm.providers["openai"].base_url

            return ChatOpenAI(
                model=model_name,
                api_key=api_key,
                base_url=base_url,
                temperature=temperature,
                timeout=timeout,
                max_retries=config.llm.max_retries,
                **kwargs,
            )

        case "groq":
            try:
                from langchain_groq import ChatGroq

                return ChatGroq(
                    model=model_name,
                    api_key=api_key,
                    temperature=temperature,
                    timeout=timeout,
                    max_retries=config.llm.max_retries,
                    **kwargs,
                )
            except ImportError:
                from langchain_openai import ChatOpenAI

                return ChatOpenAI(
                    model=model_name,
                    api_key=api_key,
                    base_url="https://api.groq.com/openai/v1",
                    temperature=temperature,
                    timeout=timeout,
                    max_retries=config.llm.max_retries,
                    **kwargs,
                )

        case "gemini":
            from langchain_google_genai import ChatGoogleGenerativeAI

            return ChatGoogleGenerativeAI(
                model=model_name,
                google_api_key=api_key,
                temperature=temperature,
                timeout=timeout,
                max_retries=config.llm.max_retries,
                **kwargs,
            )

        case "anthropic":
            from langchain_anthropic import ChatAnthropic

            return ChatAnthropic(
                model=model_name,
                api_key=api_key,
                temperature=temperature,
                timeout=timeout,
                max_retries=config.llm.max_retries,
                **kwargs,
            )

        case "ollama":
            from langchain_ollama import ChatOllama

            base_url = "http://localhost:11434"
            if "ollama" in config.llm.providers:
                provider_cfg = config.llm.providers["ollama"]
                base_url = provider_cfg.host or provider_cfg.base_url or base_url

            return ChatOllama(
                model=model_name,
                base_url=base_url,
                temperature=temperature,
                **kwargs,
            )

        case _:
            from langchain_openai import ChatOpenAI

            return ChatOpenAI(
                model=model_name,
                api_key=api_key,
                temperature=temperature,
                timeout=timeout,
                **kwargs,
            )
