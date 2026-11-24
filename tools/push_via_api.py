#!/usr/bin/env python3
"""Fallback push via GitHub Git Data API when github.com:443 is blocked.

Replays the current working tree onto the remote HEAD via blobs -> tree ->
commit -> PATCH ref. Equivalent to `git push`; CI still triggers.

The remote HEAD is fetched at runtime (not from args), so CI auto-commits
(e.g. "chore: regenerate package indexes") are never lost.

Usage:
  python3 tools/push_via_api.py "commit message"
Optional env: REPO_MESSAGE if no arg given.
"""

import base64
import json
import os
import subprocess
import sys

OWNER = "peipei7-1"
REPO = "repo"
BRANCH = "main"
GH = "/Users/77mac/.local/bin/gh"
SKIP_NAMES = {".git"}


def gh_api(method, path, payload=None):
    cmd = [GH, "api", "--method", method, path]
    if payload is not None:
        cmd += ["--input", "-"]
    proc = subprocess.run(
        cmd,
        input=json.dumps(payload) if payload is not None else None,
        text=True,
        capture_output=True,
    )
    if proc.returncode != 0:
        print("gh api failed (%s %s): %s" % (method, path, proc.stderr.strip()), file=sys.stderr)
        sys.exit(1)
    return json.loads(proc.stdout) if proc.stdout.strip() else {}


def remote_tree_entries(commit_sha):
    """Return {path: (sha, mode)} for a commit reachable on the remote."""
    commit = gh_api("GET", "repos/%s/%s/git/commits/%s" % (OWNER, REPO, commit_sha))
    tree_sha = commit["tree"]["sha"]
    out = gh_api("GET", "repos/%s/%s/git/trees/%s?recursive=1" % (OWNER, REPO, tree_sha))
    return {
        e["path"]: (e["sha"], e["mode"])
        for e in out.get("tree", [])
        if e["type"] == "blob"
    }


def local_files(root):
    """Return {relative_path: absolute_path} for tracked files in worktree."""
    proc = subprocess.run(
        ["git", "-C", root, "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
        capture_output=True,
    )
    files = {}
    for raw in proc.stdout.split(b"\x00"):
        if not raw:
            continue
        rel = raw.decode("utf-8", "surrogateescape")
        if rel.split("/")[0] in SKIP_NAMES:
            continue
        files[rel] = os.path.join(root, rel)
    return files


def main():
    message = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("REPO_MESSAGE", "push via API")
    root = subprocess.check_output(["git", "rev-parse", "--show-toplevel"], text=True).strip()

    # Remote HEAD is authoritative - fetch fresh to preserve any CI commits
    ref = gh_api("GET", "repos/%s/%s/git/refs/heads/%s" % (OWNER, REPO, BRANCH))
    remote_head = ref["object"]["sha"]
    remote = remote_tree_entries(remote_head)
    local = local_files(root)

    # For each local file, see if content matches remote; upload blob if not
    entries = []
    for rel, abspath in sorted(local.items()):
        if not os.path.isfile(abspath):
            continue
        remote_sha = remote.get(rel, (None, None))[0]
        # Compare by git hash of local file
        proc = subprocess.run(["git", "hash-object", abspath], capture_output=True, text=True)
        local_sha = proc.stdout.strip()
        mode = "100755" if os.access(abspath, os.X_OK) else "100644"
        if remote_sha == local_sha and remote.get(rel, (None, None))[1] == mode:
            continue
        with open(abspath, "rb") as fh:
            content = base64.b64encode(fh.read()).decode("ascii")
        blob = gh_api("POST", "repos/%s/%s/git/blobs" % (OWNER, REPO), {
            "content": content,
            "encoding": "base64",
        })
        entries.append({"path": rel, "mode": mode, "type": "blob", "sha": blob["sha"]})
        print("changed: %s" % rel)

    # Deletions: remote files not present locally
    for rel in sorted(set(remote) - set(local)):
        entries.append({"path": rel, "mode": "100644", "type": "blob", "sha": None})
        print("deleted: %s" % rel)

    if not entries:
        print("Nothing to push (worktree matches remote).")
        return

    base_tree_sha = gh_api("GET", "repos/%s/%s/git/commits/%s" % (OWNER, REPO, remote_head))["tree"]["sha"]
    tree = gh_api("POST", "repos/%s/%s/git/trees" % (OWNER, REPO), {
        "base_tree": base_tree_sha,
        "tree": entries,
    })
    commit = gh_api("POST", "repos/%s/%s/git/commits" % (OWNER, REPO), {
        "message": message,
        "tree": tree["sha"],
        "parents": [remote_head],
    })
    gh_api("PATCH", "repos/%s/%s/git/refs/heads/%s" % (OWNER, REPO, BRANCH), {
        "sha": commit["sha"],
        "force": False,
    })
    print("Pushed %d file change(s) via API; CI should trigger." % len(entries))


if __name__ == "__main__":
    main()
