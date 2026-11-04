from collections.abc import Iterator
from contextlib import contextmanager

from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.types import Command

from app.agent.graph import AgentState, build_graph
from app.core.config import get_settings
from app.core.llm import llm_callbacks


@contextmanager
def checkpointer(dsn: str | None = None) -> Iterator[PostgresSaver]:
    with PostgresSaver.from_conn_string(dsn or get_settings().checkpointer_dsn) as saver:
        yield saver


def setup_checkpointer() -> None:
    """Cria as tabelas do checkpointer com a role dona do schema. Roda no job
    one-off de migração; os grants para a role da app vêm dos default privileges."""
    with checkpointer(get_settings().checkpointer_admin_dsn) as saver:
        saver.setup()


def _config(thread_id: str) -> dict:
    return {"configurable": {"thread_id": thread_id}, "callbacks": llm_callbacks(),
            "run_name": "negotiation_agent"}


def run_turn(state: AgentState) -> AgentState:
    with checkpointer() as saver:
        graph = build_graph(checkpointer=saver)
        return graph.invoke({**state, "replies": [], "outcome": ""}, _config(state["thread_id"]))


def resume(thread_id: str, decision: dict) -> AgentState:
    with checkpointer() as saver:
        graph = build_graph(checkpointer=saver)
        return graph.invoke(Command(resume=decision), _config(thread_id))
