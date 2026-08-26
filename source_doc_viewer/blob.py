"""
Blob fetching through the azcopy CLI.

Same URL construction, SAS handling and resume rule as the standalone downloader
script this replaces -- the only differences are that the work list comes from the
database instead of a JSON file, and progress goes to Streamlit instead of tqdm.

A note on the SAS token: azcopy takes it as part of the URL, so it sits in the
process's argv and is visible to `ps` for the life of that azcopy process. That is
true of the existing script too and is not made worse here. What this module does
guarantee is that the token never reaches a log line, an error message or the page --
only blob paths do, and _scrub() strips the token out of azcopy's own output before
it is shown.
"""
from __future__ import annotations

import subprocess
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from pathlib import Path
from typing import Callable, Iterable, Sequence
from urllib.parse import quote

import config


class BlobError(RuntimeError):
    pass


def _scrub(text: str) -> str:
    """Never let the SAS token out, whatever azcopy decided to echo."""
    token = config.sas_token()
    if token and token in text:
        text = text.replace(token, "<sas-token>")
    return text


def _source_url(blob_path: str) -> str:
    account = config.storage_account()
    container = config.container_name()
    if not account or not container:
        raise BlobError("STORAGE_ACCOUNT and CONTAINER_NAME are not set (see the dotenv file).")

    # encode each segment separately so the slashes survive
    encoded = "/".join(quote(part, safe="") for part in str(blob_path).split("/"))
    url = f"https://{account}.blob.core.windows.net/{container}/{encoded}"
    token = config.sas_token()
    return f"{url}?{token}" if token else url


def present(dest: Path) -> bool:
    """
    The resume rule, unchanged from the downloader script: a file counts as already
    fetched only when it is non-empty, since an interrupted download can leave zero
    bytes behind.
    """
    try:
        return dest.is_file() and dest.stat().st_size > 0
    except OSError:
        return False


def fetch(blob_path: str, dest: Path) -> Path:
    """Download one blob, unless it is already there. Raises BlobError on failure."""
    if present(dest):
        return dest
    if not blob_path:
        raise BlobError("row has no blob path")

    dest.parent.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        [
            config.azcopy_bin(),
            "copy",
            _source_url(blob_path),
            str(dest),
            "--output-type=text",
            "--output-level=essential",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    if result.returncode != 0:
        detail = _scrub((result.stderr or result.stdout or "").strip())
        raise BlobError(f"azcopy failed for {blob_path}: {detail}")
    if not present(dest):
        raise BlobError(f"azcopy reported success but wrote nothing for {blob_path}")
    return dest


def fetch_many(
    jobs: Sequence[tuple[str, str, Path]],
    workers: int | None = None,
    on_done: Callable[[str, str | None], None] | None = None,
) -> dict[str, str | None]:
    """
    Download many blobs, keeping at most `workers` azcopy processes in flight and
    refilling as each finishes -- the bounded pool from the downloader script, rather
    than submitting the whole list at once.

    jobs     (job_id, blob_path, dest) triples
    on_done  called as (job_id, error_or_None) after each job settles
    returns  {job_id: None on success, else the error message}
    """
    jobs = list(jobs)
    results: dict[str, str | None] = {}
    if not jobs:
        return results

    limit = max(1, min(workers or config.workers(), len(jobs)))

    def run(job: tuple[str, str, Path]) -> None:
        _, blob_path, dest = job
        fetch(blob_path, dest)

    pending: dict[object, tuple[str, str, Path]] = {}
    remaining = iter(jobs)

    with ThreadPoolExecutor(max_workers=limit) as pool:
        for _ in range(limit):
            job = next(remaining, None)
            if job is None:
                break
            pending[pool.submit(run, job)] = job

        while pending:
            done, _ = wait(pending, return_when=FIRST_COMPLETED)
            for future in done:
                job_id, _, _ = pending.pop(future)
                try:
                    future.result()
                    error = None
                except Exception as exc:  # BlobError, OSError, anything azcopy provoked
                    error = _scrub(str(exc))
                results[job_id] = error
                if on_done is not None:
                    on_done(job_id, error)

                job = next(remaining, None)
                if job is not None:
                    pending[pool.submit(run, job)] = job

    return results
