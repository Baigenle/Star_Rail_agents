from collections.abc import AsyncIterator

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from app.core.config import Settings
from app.llm.base import LLMMessage, LLMProvider


class OpenAICompatibleProvider(LLMProvider):
    def __init__(
        self,
        *,
        name: str,
        api_key: str,
        base_url: str,
        model: str,
        temperature: float = 0.1,
        extra_body: dict | None = None,
        timeout: int = 120,
        json_mode: bool = True,
    ) -> None:
        client_kwargs: dict = {}
        if extra_body:
            client_kwargs["extra_body"] = extra_body
        model_kwargs: dict = {}
        if json_mode:
            model_kwargs["response_format"] = {"type": "json_object"}
        self.name = name
        self.client = ChatOpenAI(
            api_key=api_key,
            base_url=base_url,
            model=model,
            temperature=temperature,
            timeout=timeout,
            max_retries=2,
            model_kwargs=model_kwargs,
            **client_kwargs,
        )

    @staticmethod
    def _messages(messages: list[LLMMessage]):
        classes = {
            "system": SystemMessage,
            "assistant": AIMessage,
            "user": HumanMessage,
        }
        return [classes.get(message.role, HumanMessage)(content=message.content) for message in messages]

    async def complete(self, messages: list[LLMMessage]) -> str:
        response = await self.client.ainvoke(self._messages(messages))
        return str(response.content)

    async def stream(self, messages: list[LLMMessage]) -> AsyncIterator[str]:
        async for chunk in self.client.astream(self._messages(messages)):
            if chunk.content:
                yield str(chunk.content)


def create_llm_provider(
    settings: Settings, *, workload: str = "reasoning"
) -> LLMProvider | None:
    provider = settings.default_llm_provider.lower().strip()
    if provider == "deepseek" and settings.deepseek_api_key:
        model = (
            settings.deepseek_flash_model
            if workload == "fast"
            else settings.deepseek_pro_model
        )
        return OpenAICompatibleProvider(
            name=f"deepseek-{'flash' if workload == 'fast' else 'pro'}",
            api_key=settings.deepseek_api_key,
            base_url=settings.deepseek_base_url,
            model=model or settings.deepseek_model,
            temperature=settings.llm_temperature,
        )
    if provider == "qwen" and settings.qwen_api_key:
        return OpenAICompatibleProvider(
            name=f"qwen-{'fast' if workload == 'fast' else 'reasoning'}",
            api_key=settings.qwen_api_key,
            base_url=settings.qwen_base_url,
            model=settings.qwen_model,
            temperature=settings.llm_temperature,
        )
    if provider == "zhipu" and settings.zhipu_api_key:
        # 智谱 4.5+ 系列默认开启思考链（单次可拖到 25s+ 且延迟方差大）。
        # 常规档位关思考换稳定低延迟；ReAct 深度思考档显式开启思考。
        thinking_off = {"thinking": {"type": "disabled"}}
        if workload == "deep":
            # ReAct 深度思考档：旗舰模型 + 思考链，用于配队/剧情/复合问题的
            # 多轮推理循环。思考会显著拉长延迟（单次可到 3 分钟），放宽超时。
            return OpenAICompatibleProvider(
                name="zhipu-deep",
                api_key=settings.zhipu_api_key,
                base_url=settings.zhipu_base_url,
                model=settings.zhipu_intent_model or settings.zhipu_pro_model,
                temperature=settings.llm_temperature,
                extra_body={"thinking": {"type": "enabled"}},
                timeout=240,
            )
        if workload == "intent":
            # 意图理解专用档：更高阶模型，复杂任务拆解质量优先。
            # 高阶模型不可用时自动回退 pro，保证意图链路永不为空。
            return OpenAICompatibleProvider(
                name="zhipu-intent",
                api_key=settings.zhipu_api_key,
                base_url=settings.zhipu_base_url,
                model=settings.zhipu_intent_model or settings.zhipu_pro_model,
                temperature=settings.llm_temperature,
                extra_body=thinking_off,
            )
        model = (
            settings.zhipu_flash_model
            if workload == "fast"
            else settings.zhipu_pro_model
        )
        return OpenAICompatibleProvider(
            name=f"zhipu-{'flash' if workload == 'fast' else 'pro'}",
            api_key=settings.zhipu_api_key,
            base_url=settings.zhipu_base_url,
            model=model or settings.zhipu_model,
            temperature=settings.llm_temperature,
            extra_body=thinking_off,
        )
    return None


def create_fc_llm_provider(settings: Settings) -> ChatOpenAI | None:
    """FC 主循环专用客户端（裸 ChatOpenAI，无 response_format）。

    实测（fc_model_compare.py 探针）：tools 与 response_format=json_object 同请求
    在客户端直接抛 ValueError（"Only strict function tools can be auto-parsed"），
    请求根本不出网——FC 路径必须用本函数，不能用 OpenAICompatibleProvider。
    """
    provider = settings.default_llm_provider.lower().strip()
    if provider == "zhipu" and settings.zhipu_api_key:
        # 与现役主循环同款：glm-4.7 关思考，协议服从好、4-8s/步（Q5 实测 7/7）
        return ChatOpenAI(
            api_key=settings.zhipu_api_key,
            base_url=settings.zhipu_base_url,
            model=settings.zhipu_intent_model or settings.zhipu_pro_model,
            temperature=settings.llm_temperature,
            timeout=120,
            max_retries=2,
            extra_body={"thinking": {"type": "disabled"}},
        )
    if provider == "deepseek" and settings.deepseek_api_key:
        return ChatOpenAI(
            api_key=settings.deepseek_api_key,
            base_url=settings.deepseek_base_url,
            model=settings.deepseek_flash_model or settings.deepseek_model,
            temperature=settings.llm_temperature,
            timeout=120,
            max_retries=2,
        )
    return None
