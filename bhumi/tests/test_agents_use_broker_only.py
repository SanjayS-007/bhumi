"""Static proof that neither agent bypasses BEDROCK's real MCP protocol
boundary (kickoff prompt §4.4, hardened by the later MCP-server kickoff's
§2.3): parse each agent module's own import statements and assert
`bhumi.storage` / `bhumi.knowledge` never appear, and that the *only*
`bhumi.broker` submodule ever imported is `bhumi.broker.mcp_client` — not
`bhumi.broker.server`/`authz`/`package`, which would be an in-process
shortcut around the protocol boundary the agents are supposed to cross
for real."""
import ast
from pathlib import Path

AGENT_FILES = [
    Path(__file__).resolve().parents[1] / "src" / "bhumi" / "agents" / "pq_desk.py",
    Path(__file__).resolve().parents[1] / "src" / "bhumi" / "agents" / "report_engine.py",
]


def _imported_modules(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    modules = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            modules.append(node.module)
        elif isinstance(node, ast.Import):
            modules += [n.name for n in node.names]
    return modules


def test_agents_never_import_storage_or_knowledge_directly():
    for path in AGENT_FILES:
        modules = _imported_modules(path)
        forbidden = [m for m in modules if m.startswith("bhumi.storage") or m.startswith("bhumi.knowledge")]
        assert not forbidden, f"{path.name} imports {forbidden} directly, bypassing the broker"
        broker_imports = [m for m in modules if m.startswith("bhumi.broker")]
        assert broker_imports, f"{path.name} doesn't go through the broker at all"
        non_client = [m for m in broker_imports if m != "bhumi.broker.mcp_client"]
        assert not non_client, f"{path.name} imports {non_client} directly — must cross the real MCP protocol boundary via mcp_client only"
