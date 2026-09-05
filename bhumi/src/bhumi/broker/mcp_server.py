"""BEDROCK as a real MCP server over stdio — the actual protocol boundary
between agent and broker, replacing the previous session's in-process
Python-import boundary. Run standalone: `python -m bhumi.broker.mcp_server`.

Transport: stdio, chosen deliberately over SSE/HTTP. Stdio needs no port
management on a locked-down machine, is what Claude Code and most current
MCP clients use by default, and is the transport this server is actually
tested against. SSE/HTTP is the documented upgrade path for whenever a
future service needs to connect over a network rather than as a local
subprocess — `TRANSPORT` below is a config value precisely so that switch
is a config change later, not a rewrite; no SSE/HTTP code exists yet
because there is no real need for it yet.

Principal resolution over stdio: MCP's spec covers *authentication*
(proving who's connecting), not *authorization scoping* — that remains
this server's own responsibility, same finding as the original design
research. Stdio has no HTTP header to carry a bearer token, so the
Principal is resolved once, at process startup, from an environment
variable set at subprocess launch (`BHUMI_CALLER_ROLE` = "public" |
"internal") and held for that connection's lifetime. This is the
stdio-appropriate substitute for a bearer token — written as its own
function (`_resolve_principal`) so a future SSE/HTTP transport can instead
resolve a Principal per-request from a real auth header without touching
any tool logic. This mechanism is the part of this design most likely to
need adjustment once more real MCP clients exist; flagged, not asserted
as final.
"""
from __future__ import annotations

import json
import os

from mcp.server import Server
from mcp.types import TextContent, Tool

from bhumi.broker import server as impl
from bhumi.broker.authz import CMPDI_GEOLOGIST, INTERNAL_REVIEWER, PUBLIC_CALLER, TOOLS, AccessDenied, Principal, subsidiary_officer
from bhumi.config.settings import get_settings
from bhumi.storage.db.engine import make_engine, raw_sqlite_connection

TRANSPORT = os.environ.get("BHUMI_MCP_TRANSPORT", "stdio")  # config value, not a hardcoded choice
TOOL_SURFACE_VERSION = "1.0.0"

_STR = {"type": "string"}
_INT = {"type": "integer"}
_STR_LIST = {"type": "array", "items": {"type": "string"}}

_TOOL_SCHEMAS = {
    "search_evidence": {"query": _STR, "k": _INT},
    "get_fact": {"metric_key": _STR, "entity_id": _STR},
    "compute_metric": {"metric_key": _STR, "entity_id": _STR},
    "get_provenance": {"kind": _STR, "node_id": _STR},
    "check_coverage": {"metric_key": _STR, "entity_id": _STR},
    "seal_evidence_package": {"intent": _STR, "query": _STR, "metric_keys": _STR_LIST},
    "record_answer": {"answer_id": _STR, "package_id": _STR},
    "get_trace_graph": {"kind": _STR, "node_id": _STR},
    "revision_impact": {"fact_id": _STR, "new_value": _STR, "tolerance": _STR},
    "list_review_queue": {"doc_id": _STR},
    "list_geological_tables": {"doc_id": _STR},
    "get_conformance_report": {"doc_id": _STR},
    "merge_packages": {"package_ids": _STR_LIST, "intent": _STR},
    "replay": {"package_id": _STR},
}


def _resolve_principal() -> Principal:
    """Three personas (addon 3 §4.2), resolved from env vars set at
    subprocess launch — see module docstring on why stdio has no header
    to carry this instead. `subsidiary_officer` additionally reads
    `BHUMI_CALLER_ENTITY_SCOPE` (comma-separated doc_ids) since its whole
    point is that the scope varies by which subsidiary is connecting."""
    role = os.environ.get("BHUMI_CALLER_ROLE", "public").lower()
    if role == "internal":
        return INTERNAL_REVIEWER
    if role == "public":
        return PUBLIC_CALLER
    if role == "cmpdi_geologist":
        return CMPDI_GEOLOGIST
    if role == "subsidiary_officer":
        doc_ids = [d.strip() for d in os.environ.get("BHUMI_CALLER_ENTITY_SCOPE", "").split(",") if d.strip()]
        return subsidiary_officer(doc_ids)
    raise ValueError(f"unknown BHUMI_CALLER_ROLE={role!r}, expected public/internal/cmpdi_geologist/subsidiary_officer")


def _visible_tools(principal: Principal) -> list[Tool]:
    """Filtered by this Principal's scopes — all four personas share the
    same `TOOLS` scope today (the real distinctions are `max_
    classification` and `entity_scope`, enforced inside each tool, not
    in which tools are visible), but the filter is real: a future
    persona with a narrower tool scope would see a shorter list at the
    protocol layer, not just get an AccessDenied after asking for a tool
    it couldn't see."""
    return [
        Tool(name=name, description=f"BEDROCK tool: {name}", inputSchema={
            "type": "object", "properties": _TOOL_SCHEMAS.get(name, {}),
        })
        for name in TOOLS if name in principal.scopes
    ]


def build_server() -> Server:
    server = Server("bedrock")
    settings = get_settings()
    engine = make_engine(settings)
    raw_conn = raw_sqlite_connection(settings)
    principal = _resolve_principal()

    from sqlalchemy.orm import Session
    session = Session(engine)

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        return _visible_tools(principal)

    @server.call_tool()
    async def call_tool(name: str, arguments: dict) -> list[TextContent]:
        try:
            if name == "search_evidence":
                result = impl.search_evidence(session, raw_conn, principal, arguments["query"], arguments.get("k", 5))
            elif name == "get_fact":
                result = impl.get_fact(session, principal, arguments["metric_key"], arguments.get("entity_id"))
            elif name == "compute_metric":
                result = impl.compute_metric(session, principal, arguments["metric_key"], arguments.get("entity_id"))
            elif name == "get_provenance":
                result = impl.get_provenance(session, principal, arguments["kind"], arguments["node_id"])
            elif name == "check_coverage":
                result = impl.check_coverage(session, principal, arguments["metric_key"], arguments.get("entity_id"))
            elif name == "seal_evidence_package":
                pkg = impl.seal_evidence_package(
                    session, raw_conn, principal, arguments["intent"],
                    arguments.get("query"), arguments.get("metric_keys"),
                )
                result = pkg.to_dict()
            elif name == "record_answer":
                impl.record_answer(session, principal, arguments["answer_id"], arguments["package_id"])
                result = {"ok": True}
            elif name == "get_trace_graph":
                result = impl.get_trace_graph(session, principal, arguments["kind"], arguments["node_id"])
            elif name == "revision_impact":
                result = impl.revision_impact(session, principal, arguments["fact_id"], arguments["new_value"], arguments.get("tolerance", "0.01"))
            elif name == "list_review_queue":
                result = impl.list_review_queue(session, principal, arguments.get("doc_id"))
            elif name == "list_geological_tables":
                result = impl.list_geological_tables(session, principal, arguments["doc_id"])
            elif name == "get_conformance_report":
                result = impl.get_conformance_report(session, principal, arguments["doc_id"])
            elif name == "merge_packages":
                result = impl.merge_packages(session, principal, arguments["package_ids"], arguments["intent"])
            elif name == "replay":
                result = impl.replay(session, principal, arguments["package_id"])
            else:
                # not a real tool at all — still route through authorize()
                # so the attempt is audited, not silently rejected before
                # ever reaching the log (addon 3 §4.2: EVERY decision).
                # `name` is never in any principal's scopes, so this always
                # raises AccessDenied itself (and logs it) — no unreachable
                # fallback raise needed after it.
                from bhumi.broker.authz import authorize as _authorize
                _authorize(session, principal, name)
        except AccessDenied as e:
            return [TextContent(type="text", text=json.dumps({"error": str(e)}))]
        return [TextContent(type="text", text=json.dumps(result, default=str))]

    @server.list_resources()
    async def list_resources():
        from mcp.types import Resource
        return [Resource(
            uri="bedrock://meta/tools", name="BEDROCK tool surface", mimeType="application/json",
            description="Stable tool names + semantic version, for future MCP clients to check compatibility against.",
        )]

    @server.read_resource()
    async def read_resource(uri: str) -> str:
        if str(uri) == "bedrock://meta/tools":
            return json.dumps({"version": TOOL_SURFACE_VERSION, "tools": sorted(TOOLS)})
        raise ValueError(f"no such resource: {uri}")

    return server


async def main() -> None:
    from mcp.server.stdio import stdio_server

    if TRANSPORT != "stdio":
        raise NotImplementedError(f"transport {TRANSPORT!r} not implemented — only 'stdio' exists so far")

    server = build_server()
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
