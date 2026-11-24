#!/usr/bin/env python3
"""Generate Packages / Packages.gz / Packages.bz2 / Release for a Sileo/Cydia repo.

Pure-stdlib, no dpkg-deb needed. Works on macOS and Linux CI.
Reads .deb files from ./debs, parses their control metadata, and writes:
  Packages       - plain index
  Packages.gz    - gzip index (Sileo downloads this)
  Packages.bz2   - bzip2 index (Cydia / older clients)
  Release        - repo metadata + checksums
Optional per-package extras (auto-detected by Package name):
  icons/<Package>.png        -> Icon: field
  depictions/<Package>.json  -> Depiction: / SileoDepiction: fields
Release.gpg is intentionally omitted (unsigned repo, fine for Sileo/Zebra).
"""

import bz2
import gzip
import hashlib
import io
import os
import sys
import tarfile
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.abspath(__file__))
DEBS_DIR = os.path.join(ROOT, "debs")
ICON_DIR = os.path.join(ROOT, "icons")
DEPICTION_DIR = os.path.join(ROOT, "depictions")

ORIGIN = os.environ.get("REPO_ORIGIN", "七七爱睡懒觉")
LABEL = os.environ.get("REPO_LABEL", "七七爱睡懒觉")
SUITE = os.environ.get("REPO_SUITE", "stable")
CODENAME = os.environ.get("REPO_CODENAME", "stable")
DESCRIPTION = os.environ.get("REPO_DESCRIPTION", "七七爱睡懒觉的 iOS 越狱插件源")
ARCHITECTURES = os.environ.get("REPO_ARCHITECTURES", "iphoneos-arm64 iphoneos-arm all")

# Icon / Depiction URL base (GitHub Pages address)
BASE_URL = os.environ.get("REPO_BASE_URL", "https://peipei7-1.github.io/repo").rstrip("/")

INDEX_FILES = ("Packages", "Packages.gz", "Packages.bz2")


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
            if os.path.basename(member.name) == "control":
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


def hash_file(path, algo):
    h = hashlib.new(algo)
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

            # Auto-detect optional Icon / Depiction by Package name
            pkg_name = next((v for k, v in fields if k.lower() == "package"), None)
            if pkg_name:
                icon = os.path.join(ICON_DIR, pkg_name + ".png")
                if os.path.isfile(icon):
                    fields.append(("Icon", "%s/icons/%s.png" % (BASE_URL, pkg_name)))
                dep = os.path.join(DEPICTION_DIR, pkg_name + ".json")
                if os.path.isfile(dep):
                    url = "%s/depictions/%s.json" % (BASE_URL, pkg_name)
                    fields.append(("Depiction", url))
                    fields.append(("SileoDepiction", url))

            fields.extend([
                ("Filename", "debs/" + name),
                ("Size", str(os.path.getsize(full))),
                ("SHA256", hash_file(full, "sha256")),
                ("MD5sum", hash_file(full, "md5")),
            ])
            blocks.append("\n".join("%s: %s" % (k, v) for k, v in fields))
            print("indexed: %s" % name)
        except Exception as exc:
            print("WARN skipping %s: %s" % (name, exc), file=sys.stderr)

    packages = ("\n\n".join(blocks) + "\n") if blocks else ""
    with open(os.path.join(ROOT, "Packages"), "w", encoding="utf-8") as fh:
        fh.write(packages)

    raw = packages.encode("utf-8")
    with gzip.open(os.path.join(ROOT, "Packages.gz"), "wb") as fh:
        fh.write(raw)
    with open(os.path.join(ROOT, "Packages.bz2"), "wb") as fh:
        fh.write(bz2.compress(raw))

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
    ]
    for algo_label, algo in (("MD5Sum", "md5"), ("SHA256", "sha256")):
        release.append(algo_label + ":")
        for fname in INDEX_FILES:
            fpath = os.path.join(ROOT, fname)
            release.append(" %s %16d %s" % (hash_file(fpath, algo), os.path.getsize(fpath), fname))
    release.append("")

    with open(os.path.join(ROOT, "Release"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(release))

    print("wrote %s (%d packages), Release" % (", ".join(INDEX_FILES), len(blocks)))


if __name__ == "__main__":
    main()
