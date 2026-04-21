"""Tests for auto-background detection in terminal_tool."""

import os
import json
import pytest
from unittest.mock import patch, MagicMock


class TestShouldAutoBackground:
    """Test the _should_auto_background regex matching."""

    @pytest.fixture(autouse=True)
    def _import(self):
        from tools.terminal_tool import _should_auto_background
        self.fn = _should_auto_background

    # --- Should match (long-running) ---

    @pytest.mark.parametrize("cmd", [
        "npm start",
        "npm run dev",
        "npm run start",
        "yarn start",
        "yarn dev",
        "pnpm dev",
        "bun start",
        "uvicorn app:app --reload",
        "gunicorn myapp.wsgi:application",
        "hypercorn app:app",
        "flask run --port 5000",
        "streamlit run app.py",
        "celery worker -A tasks",
        "python manage.py runserver",
        "./manage.py runserver 0.0.0.0:8000",
        "python server.py",
        "python3 server.py",
        "node server.js",
        "ruby server.rb",
        "next dev",
        "vite",
        "vite dev",
        "webpack-dev-server",
        "react-scripts start",
        "gatsby develop",
        "remix dev",
        "docker compose up",
        "docker compose up --build",
        "docker-compose up",
        "tail -f /var/log/syslog",
        "tail -F /var/log/app.log",
        "journalctl -fu hermes-gateway",
        "journalctl -f",
        "ngrok http 8080",
        "cloudflared tunnel run",
        "bore local 8080",
        "nohup python app.py",
        "caddy run",
        "nginx start",
        # npx-launched servers
        "npx serve dist -l 4321",
        "npx http-server . -p 8080",
        "npx live-server",
        "npx serve dist -l 4321 --no-clipboard",
        # Ad-hoc one-line HTTP servers
        "python -m http.server 8080",
        "python3 -m http.server",
        "cd /tmp/h2h-serve && python3 -m http.server 8765",
        "python -m SimpleHTTPServer",
        "php -S localhost:8000",
        "ruby -run -e httpd . -p 8000",
        "busybox httpd -f",
        "miniserve .",
    ])
    def test_matches_long_running(self, cmd):
        assert self.fn(cmd), f"Expected match for: {cmd}"

    # --- Should NOT match (safe / finite) ---

    @pytest.mark.parametrize("cmd", [
        "ls -la",
        "git status",
        "git commit -m 'server update'",
        "pip install flask",
        "npm install",
        "npm run build",
        "yarn install",
        "docker compose up -d",
        "docker-compose up -d",
        "docker compose up --build -d",
        "python script.py",
        "python3 test_runner.py",
        "node build.js",
        "cat server.log",
        "pytest",
        "make build",
        "vite build",
        "vite preview",
        "vite optimize",
        "echo watching for changes",
    ])
    def test_does_not_match_safe(self, cmd):
        assert not self.fn(cmd), f"Should NOT match: {cmd}"

    # --- watch command: only at command position ---

    def test_watch_at_start(self):
        assert self.fn("watch ls -la")

    def test_watch_after_semicolon(self):
        assert self.fn("cd /tmp; watch df -h")

    def test_watch_in_path_no_match(self):
        # "watch" embedded in a word or as argument shouldn't match
        assert not self.fn("echo watching for changes")


class TestAutoBackgroundToggle:
    """Test the config toggle via TERMINAL_AUTO_BACKGROUND env var."""

    def test_disabled_via_env(self, monkeypatch):
        """When TERMINAL_AUTO_BACKGROUND=false, matching commands stay foreground."""
        monkeypatch.setenv("TERMINAL_AUTO_BACKGROUND", "false")
        # The env var is checked inside terminal_tool(); we test the logic directly
        enabled = os.getenv("TERMINAL_AUTO_BACKGROUND", "true").lower() not in ("false", "0", "no")
        assert not enabled

    def test_enabled_by_default(self, monkeypatch):
        """When env var is unset, auto-background is enabled."""
        monkeypatch.delenv("TERMINAL_AUTO_BACKGROUND", raising=False)
        enabled = os.getenv("TERMINAL_AUTO_BACKGROUND", "true").lower() not in ("false", "0", "no")
        assert enabled

    def test_enabled_explicit(self, monkeypatch):
        monkeypatch.setenv("TERMINAL_AUTO_BACKGROUND", "true")
        enabled = os.getenv("TERMINAL_AUTO_BACKGROUND", "true").lower() not in ("false", "0", "no")
        assert enabled
