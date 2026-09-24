"""Streaming reader for nested NF525 zip archives."""

from __future__ import annotations

import hashlib
import io
import zipfile
from dataclasses import dataclass
from pathlib import Path
from tempfile import SpooledTemporaryFile

from src.ingestion.names import is_safe_zip_member


@dataclass
class NestedArchiveContent:
    archive_name: str
    sha256: str
    byte_size: int
    html_bytes: bytes
    rsa_signature: str
    html_filename: str


@dataclass
class RootArchiveMember:
    info: zipfile.ZipInfo
    sha256: str


def iter_root_members(root_path: Path) -> list[RootArchiveMember]:
    """List nested zip members from a root archive with SHA-256 hashes."""
    members: list[RootArchiveMember] = []
    with zipfile.ZipFile(root_path) as root_zip:
        for info in root_zip.infolist():
            if info.is_dir():
                continue
            if not info.filename.lower().endswith(".zip"):
                continue
            if not is_safe_zip_member(info.filename):
                continue
            sha256 = _hash_member(root_zip, info)
            members.append(RootArchiveMember(info=info, sha256=sha256))
    return members


def read_nested_archive(root_path: Path, member: RootArchiveMember) -> NestedArchiveContent:
    """Spool and read a nested archive's HTML and RSA content."""
    with zipfile.ZipFile(root_path) as root_zip:
        with root_zip.open(member.info) as source:
            spool = SpooledTemporaryFile(max_size=8 * 1024 * 1024)
            while True:
                chunk = source.read(1024 * 1024)
                if not chunk:
                    break
                spool.write(chunk)
            spool.seek(0)
            byte_size = spool.tell()
            spool.seek(0)

            with zipfile.ZipFile(spool) as inner_zip:
                html_names = [n for n in inner_zip.namelist() if n.lower().endswith(".html")]
                rsa_names = [n for n in inner_zip.namelist() if n.lower().endswith(".rsa")]

                if not html_names:
                    raise ValueError("No HTML file in nested archive")

                html_name = html_names[0]
                html_bytes = inner_zip.read(html_name)
                rsa_signature = ""
                if rsa_names:
                    rsa_signature = inner_zip.read(rsa_names[0]).decode("utf-8-sig", errors="replace").strip()

    return NestedArchiveContent(
        archive_name=member.info.filename,
        sha256=member.sha256,
        byte_size=byte_size,
        html_bytes=html_bytes,
        rsa_signature=rsa_signature,
        html_filename=html_name,
    )


def _hash_member(root_zip: zipfile.ZipFile, info: zipfile.ZipInfo) -> str:
    digest = hashlib.sha256()
    with root_zip.open(info) as source:
        while True:
            chunk = source.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()
