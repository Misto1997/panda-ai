"""Wires the nodes into the LangGraph workflow:  route -> plan (retrieve, generate SQL, guard, dry-run, repair | IR fallback) -> execute -> respond | rca | discover | help"""
from __future__ import annotations

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph

from app.agents.base import AgentNode
from app.agents.deps import NodeDependencies
from app.agents.nodes.discovery import DiscoveryNode
from app.agents.nodes.executor import ExecutorNode, after_execute
from app.agents.nodes.help import HelpNode
from app.agents.nodes.meta import MetaNode
from app.agents.nodes.narrate import NarrateNode
from app.agents.nodes.planner import SqlPlannerNode
from app.agents.nodes.rca import RcaNode
from app.agents.nodes.responder import ResponderNode
from app.agents.nodes.router import RouterNode, after_route
from app.agents.state import TurnState
from app.core.enums import NodeName

NODE_CLASSES: list[type[AgentNode]] = [RouterNode, SqlPlannerNode, ExecutorNode, ResponderNode, NarrateNode, RcaNode, DiscoveryNode, HelpNode, MetaNode]


def build_graph(deps: NodeDependencies, checkpointer: BaseCheckpointSaver):
    graph = StateGraph(TurnState)
    for cls in NODE_CLASSES:
        graph.add_node(cls.name.value, cls(deps))
    graph.add_edge(START, NodeName.ROUTE.value)
    graph.add_conditional_edges(NodeName.ROUTE.value, after_route,
                                [NodeName.PLAN.value, NodeName.RCA.value, NodeName.DISCOVER.value, NodeName.HELP.value, NodeName.META.value, END])
    graph.add_conditional_edges(NodeName.PLAN.value, lambda s: END if s.get("response") else NodeName.EXECUTE.value, [NodeName.EXECUTE.value, END])
    graph.add_conditional_edges(NodeName.EXECUTE.value, after_execute, [NodeName.RESPOND.value, END])
    graph.add_edge(NodeName.RESPOND.value, NodeName.NARRATE.value)  # data first, optional prose after
    graph.add_edge(NodeName.RCA.value, NodeName.NARRATE.value)
    for terminal in (NodeName.NARRATE, NodeName.DISCOVER, NodeName.HELP, NodeName.META):
        graph.add_edge(terminal.value, END)
    return graph.compile(checkpointer=checkpointer)
