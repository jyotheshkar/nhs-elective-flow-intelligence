"""Offline regressions for atomic, bounded source downloads."""

from datetime import date
from types import SimpleNamespace

import httpx
import pytest

from app.ingestion import downloader
from app.ingestion.discovery import DiscoveredFile


@pytest.fixture
def source(tmp_path, monkeypatch):
    monkeypatch.setattr(downloader, "get_settings", lambda: SimpleNamespace(
        raw_dir=tmp_path, ensure_directories=lambda: None,
    ))
    monkeypatch.setattr(downloader, "get_source_config", lambda: {
        "ingestion": {"max_retries": 1, "max_download_bytes": 8},
    })
    return DiscoveredFile(
        dataset="incomplete", reporting_month=date(2026, 6, 1),
        url="https://example.test/Incomplete-Jun26.xlsx",
        filename="Incomplete-Jun26.xlsx", revision=0, source_page="fixture",
    )


def test_success_records_checksum_and_leaves_no_partial(source, tmp_path):
    with httpx.Client(transport=httpx.MockTransport(
        lambda request: httpx.Response(200, content=b"workbook"),
    )) as client:
        result = downloader.download_file(source, client)
    assert result.status == "downloaded"
    assert result.local_path.read_bytes() == b"workbook"
    assert result.bytes_downloaded == 8
    assert result.checksum_sha256 == downloader._sha256(result.local_path)
    assert list(tmp_path.rglob("*.part")) == []


@pytest.mark.parametrize("payload", [b"", b"oversized"])
def test_invalid_download_preserves_existing_cache(source, tmp_path, payload):
    target = tmp_path / source.dataset / source.filename
    target.parent.mkdir()
    target.write_bytes(b"old")
    with httpx.Client(transport=httpx.MockTransport(
        lambda request: httpx.Response(200, content=payload),
    )) as client:
        result = downloader.download_file(source, client, force=True)
    assert result.status == "failed"
    assert target.read_bytes() == b"old"
    assert list(tmp_path.rglob("*.part")) == []


def test_interrupted_stream_is_cleaned(source, tmp_path):
    class Interrupted(httpx.SyncByteStream):
        def __iter__(self):
            yield b"first"
            raise httpx.ReadError("connection lost")

    with httpx.Client(transport=httpx.MockTransport(
        lambda request: httpx.Response(200, stream=Interrupted()),
    )) as client:
        result = downloader.download_file(source, client)
    assert result.status == "failed"
    assert not (tmp_path / source.dataset / source.filename).exists()
    assert list(tmp_path.rglob("*.part")) == []


@pytest.mark.parametrize("field,value", [
    ("filename", "../outside.xlsx"), ("filename", "..\\outside.xlsx"),
    ("dataset", "../outside"), ("dataset", ".."),
])
def test_rejects_path_components(source, field, value):
    from dataclasses import replace

    with httpx.Client(transport=httpx.MockTransport(
        lambda request: httpx.Response(200, content=b"unused"),
    )) as client, pytest.raises(ValueError, match="path component"):
        downloader.download_file(replace(source, **{field: value}), client)
