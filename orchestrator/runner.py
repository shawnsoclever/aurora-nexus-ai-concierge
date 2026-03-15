from __future__ import annotations

from core.llm import configure_runtime_environment
from core.session import session_manager

# Ensure ADK/GenAI clients always see API credentials, even when this module
# is executed directly outside the FastAPI app bootstrap path.
configure_runtime_environment()


_runner = None


def _get_runner_and_types():
    global _runner
    if _runner is not None:
        from google.genai.types import Content, Part

        return _runner, Content, Part

    from google.adk.runners import Runner
    from google.genai.types import Content, Part

    from agents.orchestrator import build_root_orchestrator

    _root_agent = build_root_orchestrator()
    _runner = Runner(
        agent=_root_agent,
        app_name=session_manager.app_name,
        session_service=session_manager.service,
    )
    return _runner, Content, Part


async def run_agent(*, user_id: str, session_id: str, message: str) -> str:
    await session_manager.ensure_session(user_id=user_id, session_id=session_id)

    runner, Content, Part = _get_runner_and_types()

    user_message = Content(role="user", parts=[Part(text=message)])
    final_response = ""

    async for event in runner.run_async(
        user_id=user_id,
        session_id=session_id,
        new_message=user_message,
    ):
        if event.is_final_response() and event.content and event.content.parts:
            final_response = "\n".join(part.text or "" for part in event.content.parts)

    return final_response
