#!/usr/bin/env python3
"""Generate Packages / Packages.gz / Release indexes for a Sileo/Cydia repo.

Pure-stdlib, no dpkg-deb needed. Works on macOS and Linux CI.
Reads .deb files from ./debs, parses their control metadata, and writes:
  Packages       - plain index
  Packages.gz    - gzip index (what Sileo actually downloads)
  Release        - repo metadata + checksums
  Release.gpg is intentionally omitted (unsigned repo, fine for Sileo/Zebra).
"""

import gzip
import hashlib
import os
import re
import sys
import tarfile
import io
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.abspath(__file__))
DEBS_DIR = os.path.join(ROOT, "debs")

ORIGIN = os.environ.get("REPO_ORIGIN", "peipei7-1 Repo")
LABEL = os.environ.get("REPO_LABEL", "peipei7-1 Repo")
SUITE = os.environ.get("REPO_SUITE", "stable")
CODENAME = os.environ.get("REPO_CODENAME", "stable")
DESCRIPTION = os.environ.get("REPO_DESCRIPTION", "Personal iOS jailbreak tweak repository")
ARCHITECTURES = os.environ.get("REPO_ARCHITECTURES", "iphoneos-arm64 iphoneos-arm all")


def read_deb_control(path):
    """Extract the control file bytes from a .deb (ar archive)."""
    with open(path, "rb") as fh:
        magic = fh.read(8)
        if magic != b"!<arch>\n":
            raise ValueError("not an ar archive: %s" % path)
        members = {}
        while True:
            header = fh.read(60)
            if len(header) < 60:
                break
            name = header[:16].decode("ascii", "replace").strip().rstrip("/")
            try:
                size = int(header[48:58].decode("ascii", "replace").strip())
            except ValueError:
                raise ValueError("bad ar member size in %s" % path)
            data = fh.read(size)
            if size % 2:
                fh.read(1)
            members[name] = data

    ctrl_blob = None
    for name, data in members.items():
        if name.startswith("control.tar"):
            if name.endswith(".gz"):
                data = gzip.decompress(data)
            elif name.endswith(".xz") or name.endswith(".lzma"):
                import lzma
                data = lzma.decompress(data)
            elif name.endswith(".zst"):
                try:
                    import zstandard
                    data = zstandard.ZstdDecompressor().decompress(data)
                except ImportError:
                    raise RuntimeError("zstd-compressed control.tar needs 'zstandard' module")
            ctrl_blob = data
            break
    if ctrl_blob is None:
        raise ValueError("no control.tar found in %s" % path)

    with tarfile.open(fileobj=io.BytesIO(ctrl_blob), mode="r:") as tf:
        for member in tf.getmembers():
            base = os.path.basename(member.name)
            if base == "control":
                return tf.extractfile(member).read()
    raise ValueError("no control file inside control.tar of %s" % path)


def parse_control(raw):
    """Parse RFC822-style control into an ordered list of (key, value)."""
    text = raw.decode("utf-8", "replace")
    fields = []
    for line in text.splitlines():
        if not line.strip():
            continue
        if line[0] in " \t" and fields:
            k, v = fields[-1]
            fields[-1] = (k, v + "\n" + line.rstrip())
            continue
        if ":" in line:
            k, v = line.split(":", 1)
            fields.append((k.strip(), v.strip()))
    return fields


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def md5(path):
    h = hashlib.md5()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def main():
    if not os.path.isdir(DEBS_DIR):
        print("debs/ directory missing", file=sys.stderr)
        sys.exit(1)

    deb_files = sorted(
        f for f in os.listdir(DEBS_DIR)
        if f.endswith(".deb") and os.path.isfile(os.path.join(DEBS_DIR, f))
    )

    blocks = []
    for name in deb_files:
        full = os.path.join(DEBS_DIR, name)
        try:
            fields = parse_control(read_deb_control(full))
            fields = [(k, v) for k, v in fields if k.lower() != "sha256"]
            fields.extend([
                ("Filename", "debs/" + name),
                ("Size", str(os.path.getsize(full))),
                ("SHA256", sha256(full)),
                ("MD5sum", md5(full)),
            ])
            block = "\n".join("%s: %s" % (k, v) for k, v in fields)
            blocks.append(block)
            print("indexed: %s" % name)
        except Exception as exc:
            print("WARN skipping %s: %s" % (name, exc), file=sys.stderr)

    packages = "\n\n".join(blocks) + "\n" if blocks else ""
    pkg_path = os.path.join(ROOT, "Packages")
    with open(pkg_path, "w", encoding="utf-8") as fh:
        fh.write(packages)

    gz_path = os.path.join(ROOT, "Packages.gz")
    with gzip.open(gz_path, "wb") as fh:
        fh.write(packages.encode("utf-8"))

    now = datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S +0000")
    release = [
        "Origin: " + ORIGIN,
        "Label: " + LABEL,
        "Suite: " + SUITE,
        "Codename: " + CODENAME,
        "Date: " + now,
        "Architectures: " + ARCHITECTURES,
        "Components: main",
        "Description: " + DESCRIPTION,
        "MD5Sum:",
    ]
    for fname in ("Packages", "Packages.gz"):
        fpath = os.path.join(ROOT, fname)
        release.append(" %s %16d %s" % (md5(fpath), os.path.getsize(fpath), fname))
    release.append("SHA256:")
    for fname in ("Packages", "Packages.gz"):
        fpath = os.path.join(ROOT, fname)
        release.append(" %s %16d %s" % (sha256(fpath), os.path.getsize(fpath), fname))
    release.append("")

    with open(os.path.join(ROOT, "Release"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(release))

    print("wrote Packages (%d packages), Packages.gz, Release" % len(blocks))


if __name__ == "__main__":
    main()
