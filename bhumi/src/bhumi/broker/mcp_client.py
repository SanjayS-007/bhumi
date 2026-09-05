"""The ONLY sanctioned import surface for agents now that BEDROCK is a
real MCP server (kickoff prompt §2.3) — replaces the previous session's
`bhumi.broker.client` direct-Python-call surface. Spawns
`bhumi.broker.mcp_server` as a subprocess per call and talks to it over
the real MCP stdio protocol; nothing here imports `bhumi.storage` or
`bhumi.knowledge`.

One subprocess per call is deliberately simple, not pooled — this reduced
slice values a real protocol boundary over connection-pooling
performance, which isn't a demonstrated bottleneck at this scale (2
documents, 2 agents). `Session`/`ClientSession` pooling is a real
optimization to make later, not now.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from bhumi.broker.authz import AccessDenied

Role = str  # "public" | "internal"


async def _call_tool_async(tool_name: str, arguments: dict, role: Role, env_overrides: dict | None = None) -> dict:
    # every declared tool param is typed "string" in the input schema
    # (see mcp_server.py's _visible_tools) — an explicit None for an
    # optional arg (e.g. entity_id) fails that type check, so omit it
    # entirely rather than sending null
    arguments = {k: v for k, v in arguments.items() if v is not None}
    env = {**os.environ, "BHUMI_CALLER_ROLE": role, **(env_overrides or {})}
    params = StdioServerParameters(command=sys.executable, args=["-m", "bhumi.broker.mcp_server"], env=env)
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(tool_name, arguments)
            text = result.content[0].text
            parsed = json.loads(text)
            if isinstance(parsed, dict) and "error" in parsed and len(parsed) == 1:
                raise AccessDenied(parsed["error"])
            return parsed


async def _list_tools_async(role: Role, env_overrides: dict | None = None) -> list[str]:
    env = {**os.environ, "BHUMI_CALLER_ROLE": role, **(env_overrides or {})}
    params = StdioServerParameters(command=sys.executable, args=["-m", "bhumi.broker.mcp_server"], env=env)
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.list_tools()
            return [t.name for t in result.tools]


def _flatten_exception_group(exc: BaseException) -> list[BaseException]:
    if isinstance(exc, BaseExceptionGroup):
        flat: list[BaseException] = []
        for sub in exc.exceptions:
            flat += _flatten_exception_group(sub)
        return flat
    return [exc]


def call_tool(tool_name: str, arguments: dict, role: Role, env_overrides: dict | None = None):
    try:
        return asyncio.run(_call_tool_async(tool_name, arguments, role, env_overrides))
    except BaseExceptionGroup as eg:
        # anyio's TaskGroup wraps any exception raised while an async
        # context manager (stdio_client/ClientSession) is exiting in a
        # BaseExceptionGroup, even when there's exactly one real cause
        # (e.g. AccessDenied re-raised from a parsed error response) —
        # unwrap so callers see that real exception directly, not a
        # generic group with no useful __str__
        flat = _flatten_exception_group(eg)
        if len(flat) == 1:
            raise flat[0] from eg
        raise


def list_tools(role: Role, env_overrides: dict | None = None) -> list[str]:
    return asyncio.run(_list_tools_async(role, env_overrides))


def seal_evidence_package(intent: str, role: Role, query: str | None = None, metric_keys: list[str] | None = None, env_overrides: dict | None = None) -> dict:
    return call_tool("seal_evidence_package", {"intent": intent, "query": query, "metric_keys": metric_keys}, role, env_overrides)


def compute_metric(metric_key: str, role: Role, entity_id: str | None = None, env_overrides: dict | None = None) -> list[dict]:
    return call_tool("compute_metric", {"metric_key": metric_key, "entity_id": entity_id}, role, env_overrides)


def check_coverage(metric_key: str, role: Role, entity_id: str | None = None, env_overrides: dict | None = None) -> dict:
    return call_tool("check_coverage", {"metric_key": metric_key, "entity_id": entity_id}, role, env_overrides)


def get_provenance(kind: str, node_id: str, role: Role, env_overrides: dict | None = None) -> list[dict]:
    return call_tool("get_provenance", {"kind": kind, "node_id": node_id}, role, env_overrides)


def list_review_queue(role: Role, doc_id: str | None = None, env_overrides: dict | None = None) -> list[dict]:
    return call_tool("list_review_queue", {"doc_id": doc_id}, role, env_overrides)


def list_geological_tables(doc_id: str, role: Role, env_overrides: dict | None = None) -> list[dict]:
    return call_tool("list_geological_tables", {"doc_id": doc_id}, role, env_overrides)


def get_conformance_report(doc_id: str, role: Role, env_overrides: dict | None = None) -> dict:
    return call_tool("get_conformance_report", {"doc_id": doc_id}, role, env_overrides)


def merge_packages(package_ids: list[str], intent: str, role: Role, env_overrides: dict | None = None) -> dict:
    return call_tool("merge_packages", {"package_ids": package_ids, "intent": intent}, role, env_overrides)


def replay(package_id: str, role: Role, env_overrides: dict | None = None) -> dict:
    return call_tool("replay", {"package_id": package_id}, role, env_overrides)


def subsidiary_env(doc_ids: list[str]) -> dict:
    """Convenience for tests/callers: the env override a subsidiary
    officer needs alongside `role="subsidiary_officer"`."""
    return {"BHUMI_CALLER_ENTITY_SCOPE": ",".join(doc_ids)}


def record_answer(answer_id: str, package_id: str, role: Role, env_overrides: dict | None = None) -> dict:
    return call_tool("record_answer", {"answer_id": answer_id, "package_id": package_id}, role, env_overrides)


def get_trace_graph(kind: str, node_id: str, role: Role, env_overrides: dict | None = None) -> dict:
    return call_tool("get_trace_graph", {"kind": kind, "node_id": node_id}, role, env_overrides)


def revision_impact(fact_id: str, new_value: str, role: Role, tolerance: str = "0.01", env_overrides: dict | None = None) -> dict:
    return call_tool("revision_impact", {"fact_id": fact_id, "new_value": new_value, "tolerance": tolerance}, role, env_overrides)
