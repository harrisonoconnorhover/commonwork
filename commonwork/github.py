"""Small GitHub REST adapter; no AI provider credentials or code execution."""

from __future__ import annotations

import json
import os
import re
import subprocess
import urllib.error
import urllib.parse
import urllib.request


class GitHubError(RuntimeError):
    """A GitHub request failed without exposing credentials."""


def validate_repo(repo: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo):
        raise ValueError("Repository must be OWNER/REPOSITORY.")
    if any(part in {".", ".."} for part in repo.split("/")):
        raise ValueError("Invalid repository name.")
    return repo


def positive_number(value: str | int) -> int:
    number = int(value)
    if number < 1:
        raise ValueError("Issue or PR number must be positive.")
    return number


class _GitHubRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        target = urllib.parse.urlsplit(newurl)
        if target.scheme != "https" or target.netloc != "api.github.com":
            raise GitHubError("Refusing to forward GitHub credentials to another host.")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class GitHub:
    def __init__(self, repo: str, token: str | None = None):
        self.repo = validate_repo(repo)
        self.token = token if token is not None else self._token()
        self.opener = urllib.request.build_opener(_GitHubRedirect())

    @staticmethod
    def _token() -> str:
        token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
        if token:
            return token
        try:
            result = subprocess.run(
                ["gh", "auth", "token", "--hostname", "github.com"],
                capture_output=True, text=True, timeout=15, check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            return ""
        return result.stdout.strip() if result.returncode == 0 else ""

    def request(self, method: str, path: str, data=None):
        if not path.startswith("/") or path.startswith("//"):
            raise ValueError("Expected a relative GitHub API path.")
        if method != "GET" and not self.token:
            raise GitHubError("Sign in with `gh auth login`, or set GH_TOKEN, before writing.")
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2026-03-10",
            "User-Agent": "commonwork/0.1",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        encoded = None
        if data is not None:
            encoded = json.dumps(data).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(
            "https://api.github.com" + path, data=encoded, headers=headers, method=method
        )
        try:
            with self.opener.open(request, timeout=30) as response:
                body = response.read()
                return json.loads(body) if body else None
        except urllib.error.HTTPError as error:
            # Do not print response bodies: they may contain user data or secrets.
            raise GitHubError(
                f"GitHub returned HTTP {error.code} for {method} {path}. "
                "Check access, token permissions, and GitHub rate limits."
            ) from None
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
            raise GitHubError(f"Could not read GitHub response for {method} {path}.") from None

    def get(self, suffix: str):
        return self.request("GET", f"/repos/{self.repo}/{suffix}")

    def list(self, suffix: str) -> list[dict]:
        results = []
        page = 1
        while True:
            separator = "&" if "?" in suffix else "?"
            batch = self.get(f"{suffix}{separator}per_page=100&page={page}")
            if not isinstance(batch, list):
                raise GitHubError("GitHub returned an unexpected list response.")
            results.extend(batch)
            if len(batch) < 100:
                return results
            page += 1

    def comments(self, number: int) -> list[dict]:
        return self.list(f"issues/{positive_number(number)}/comments")

    def comment(self, number: int, body: str):
        return self.request("POST", f"/repos/{self.repo}/issues/{positive_number(number)}/comments", {"body": body})

    def upsert_summary(self, number: int, comments: list[dict], body: str, marker: str):
        # Humans cannot impersonate the Actions bot by copying its marker.
        existing = [
            c for c in comments
            if c.get("user", {}).get("login") == "github-actions[bot]"
            and c.get("user", {}).get("type") == "Bot"
            and (c.get("body") or "").startswith(marker)
        ]
        if existing:
            latest = max(existing, key=lambda c: int(c["id"]))
            if latest.get("body") == body:
                return latest
            return self.request("PATCH", f"/repos/{self.repo}/issues/comments/{int(latest['id'])}", {"body": body})
        return self.comment(number, body)
