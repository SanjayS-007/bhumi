from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table as RichTable
from sqlalchemy.orm import Session

from bhumi.config.settings import get_settings
from bhumi.env.report import write_report
from bhumi.runtime.logging import configure_logging
from bhumi.storage.db.engine import migrate as db_migrate

app = typer.Typer(add_completion=False)
console = Console()


@app.command()
def doctor(strict: bool = typer.Option(False, "--strict"), offline: bool = typer.Option(False, "--offline")):
    """Probe environment, write ENVIRONMENT_REPORT.md."""
    settings = get_settings()
    text, ok = write_report(settings, offline=offline)
    console.print(text)
    console.print(f"[bold]wrote ENVIRONMENT_REPORT.md[/bold] (strict_ok={ok})")
    if strict and not ok:
        raise typer.Exit(code=1)


@app.command()
def migrate():
    """Apply schema to the active profile (create_all — see storage/db/engine.py ponytail note)."""
    settings = get_settings()
    db_migrate(settings)
    console.print(f"[green]migrated[/green] profile={settings.profile.value} -> {settings.sqlite_path}")


@app.command()
def profile():
    """Show active profile and resolved backends."""
    settings = get_settings()
    t = RichTable(show_header=False)
    t.add_row("profile", settings.profile.value)
    t.add_row("relational", f"sqlite  {settings.sqlite_path}" if settings.profile.value == "sqlite" else "postgres")
    t.add_row("vector", f"{settings.vector_backend} (not implemented until Phase 5)")
    t.add_row("text search", f"{settings.text_backend} (not implemented until Phase 5)")
    t.add_row("graph", f"{settings.graph_backend} (not implemented until Phase 5)")
    t.add_row("blobs", f"local  {settings.data_dir / 'vault'}")
    t.add_row("read tiers", "T1 pymupdf (always) · T2 docling (extra 'read', not installed) · T3 (unavailable, no GPU)")
    console.print(t)


@app.command()
def acquire(
    file: Path = typer.Option(..., "--file"),
    doc_id: str = typer.Option(...),
    title: str = typer.Option(...),
    publisher: str = typer.Option("OTHER"),
    kind: str = typer.Option("sample", "--kind"),
    authority_rank: int = typer.Option(5, "--authority-rank"),
    status: str = typer.Option("final"),
    classification: str = typer.Option("public"),
    stage: str = typer.Option(None),
    coalfield: str = typer.Option(None),
):
    """Register + vault a source document."""
    from bhumi.acquire.registry import register_local_file

    settings = get_settings()
    engine = db_migrate(settings)
    with Session(engine) as session:
        row = register_local_file(
            session, settings, file, doc_id=doc_id, title=title, publisher=publisher,
            doc_kind=kind, authority_rank=authority_rank, status=status,
            classification=classification, stage=stage, coalfield=coalfield,
        )
    console.print(f"registered doc_id={row.doc_id} artifact_id={row.artifact_id[:12]}... pages={row.page_count}")


@app.command()
def ingest(sample: bool = typer.Option(False, "--sample"), doc_id: str = typer.Option(None)):
    """Run the READ pipeline over registered docs, or synthesize + ingest the sample doc."""
    from bhumi.acquire.registry import register_local_file
    from bhumi.read.pipeline import run_read_pipeline

    settings = get_settings()
    engine = db_migrate(settings)

    if sample:
        from scripts.make_sample_pdf import make_sample_pdf

        sample_path = settings.data_dir / "sample.pdf"
        make_sample_pdf(sample_path)
        target_doc_id = "SAMPLE-MARWATOLA-G2"
        with Session(engine) as session:
            row = register_local_file(
                session, settings, sample_path, doc_id=target_doc_id,
                title="Final Geological Report (SAMPLE) — Marwatola Sector I & II",
                publisher="CMPDI", doc_kind="sample", authority_rank=2,
                stage="G2", coalfield="Sohagpur",
            )
            ast = run_read_pipeline(session, settings, row.doc_id, row.artifact_id, sample_path)
        console.print(f"[green]ingested sample[/green] doc_id={target_doc_id} pages={len(ast.pages)} tables={len(ast.tables)}")
        return

    if not doc_id:
        console.print("[red]pass --sample or --doc-id[/red]")
        raise typer.Exit(1)

    from bhumi.storage.db.models import SourceRegistry

    with Session(engine) as session:
        row = session.query(SourceRegistry).filter_by(doc_id=doc_id).one()
        pdf_path = settings.data_dir.parent / row.vault_ref if not Path(row.vault_ref).is_absolute() else Path(row.vault_ref)
        ast = run_read_pipeline(session, settings, row.doc_id, row.artifact_id, pdf_path)
    console.print(f"ingested {doc_id}: pages={len(ast.pages)} tables={len(ast.tables)}")


@app.command()
def serve():
    """Self-healing: run doctor + migrate, then start the drill-down UI."""
    settings = get_settings()
    write_report(settings)
    db_migrate(settings)
    ui_path = Path(__file__).resolve().parents[2] / "ui" / "app.py"
    subprocess.run([sys.executable, "-m", "streamlit", "run", str(ui_path)])


@app.command()
def verify():
    """CI gate: strict doctor + tests."""
    settings = get_settings()
    _, ok = write_report(settings)
    if not ok:
        raise typer.Exit(1)
    result = subprocess.run(["pytest", "-q"])
    raise typer.Exit(result.returncode)


def main():
    configure_logging()
    app()


if __name__ == "__main__":
    main()
