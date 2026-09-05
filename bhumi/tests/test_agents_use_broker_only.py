"""Static proof that neither agent bypasses BEDROCK (kickoff prompt
§4.4): parse each agent module's own import statements and assert
`bhumi.storage` / `bhumi.knowledge` never appear, only `bhumi.broker`."""
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
        assert any(m.startswith("bhumi.broker") for m in modules), f"{path.name} doesn't go through the broker at all"
