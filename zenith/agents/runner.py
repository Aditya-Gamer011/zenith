"""Agent runner: starts a background asyncio task per agent and tracks status."""
from __future__ import annotations

from .agent_service import AgentService


class Runner:
    """Wraps the AgentService; kept as a thin facade so services can share one instance."""

    def __init__(self) -> None:
        self._svc: AgentService | None = None

    def service(self) -> AgentService:
        if self._svc is None:
            from ..core.services import get_agent_service

            self._svc = get_agent_service()
        return self._svc

    async def start(self, name: str, goal: str, context: str = "") -> str:
        return await self.service().start(name, goal, context)

    def list(self):
        return self.service().list()

    def list_roster(self):
        return self.service().list_roster()

    def get_agent_profile(self, name: str):
        return self.service().get_agent_profile(name)

    def result(self, agent_id: str) -> str:
        return self.service().result(agent_id)


runner = Runner()