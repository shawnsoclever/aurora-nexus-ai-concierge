from __future__ import annotations

from dataclasses import dataclass, field
from threading import Lock
from typing import Literal

try:
    from google.adk.sessions import InMemorySessionService
except ImportError:  # pragma: no cover - fallback for local tests without ADK
    class InMemorySessionService:  # type: ignore[override]
        def __init__(self) -> None:
            self._sessions: dict[tuple[str, str, str], dict] = {}

        async def get_session(self, *, app_name: str, user_id: str, session_id: str):
            return self._sessions.get((app_name, user_id, session_id))

        async def create_session(self, *, app_name: str, user_id: str, session_id: str):
            payload = {
                "app_name": app_name,
                "user_id": user_id,
                "session_id": session_id,
            }
            self._sessions[(app_name, user_id, session_id)] = payload
            return payload

from core.config import get_settings


WorkflowStage = Literal[
    "enquiry",
    "profiling",
    "recommendation",
    "preview",
    "payment",
    "confirmation",
]


@dataclass
class WorkflowState:
    stage: WorkflowStage = "enquiry"
    guest_profile: dict = field(default_factory=dict)
    recommended_room_ids: list[str] = field(default_factory=list)
    selected_room_id: str | None = None
    booking_preview: dict = field(default_factory=dict)
    payment_preview: dict = field(default_factory=dict)
    final_booking_id: str | None = None
    payment_confirmed: bool = False


ALLOWED_TRANSITIONS: dict[WorkflowStage, set[WorkflowStage]] = {
    "enquiry": {"profiling", "recommendation", "enquiry"},
    "profiling": {"recommendation", "profiling"},
    "recommendation": {"preview", "recommendation", "profiling"},
    "preview": {"payment", "recommendation", "preview"},
    "payment": {"confirmation", "preview", "payment"},
    "confirmation": {"confirmation", "enquiry"},
}


class SessionManager:
    def __init__(self) -> None:
        self._service = InMemorySessionService()
        settings = get_settings()
        self._app_name = f"hotel-agent-{settings.app_env}"
        self._workflow_states: dict[str, WorkflowState] = {}
        self._lock = Lock()

    @property
    def service(self) -> InMemorySessionService:
        return self._service

    async def ensure_session(self, *, user_id: str, session_id: str):
        session = await self._service.get_session(
            app_name=self._app_name,
            user_id=user_id,
            session_id=session_id,
        )
        if session:
            return session

        return await self._service.create_session(
            app_name=self._app_name,
            user_id=user_id,
            session_id=session_id,
        )

    @property
    def app_name(self) -> str:
        return self._app_name

    def get_workflow_state(self, session_id: str) -> WorkflowState:
        with self._lock:
            return self._workflow_states.setdefault(session_id, WorkflowState())

    def transition_stage(self, session_id: str, target: WorkflowStage) -> WorkflowState:
        with self._lock:
            state = self._workflow_states.setdefault(session_id, WorkflowState())
            if target not in ALLOWED_TRANSITIONS[state.stage]:
                raise ValueError(
                    f"Invalid stage transition: {state.stage} -> {target}. "
                    "Complete required steps before proceeding."
                )
            state.stage = target
            return state

    def reset_to_recommendation(self, session_id: str) -> WorkflowState:
        with self._lock:
            state = self._workflow_states.setdefault(session_id, WorkflowState())
            state.stage = "recommendation"
            state.recommended_room_ids = []
            state.selected_room_id = None
            state.booking_preview = {}
            state.payment_preview = {}
            state.payment_confirmed = False
            state.final_booking_id = None
            return state


session_manager = SessionManager()
