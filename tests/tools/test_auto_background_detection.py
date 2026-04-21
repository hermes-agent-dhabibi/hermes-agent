"""Tests for auto-background detection in terminal_tool.

This suite is the regression net for the long-running-command detector.
Whenever a foreground hang happens in production, add the offending command
here as a `should-match` case.
"""

import os
import pytest


@pytest.fixture
def fn():
    from tools.terminal_tool import _should_auto_background
    return _should_auto_background


# ─── SHOULD AUTO-BACKGROUND ───────────────────────────────────────────────

# Group cases by category so failures are easy to locate.
SHOULD_MATCH = {
    # === Make / task runners ===
    "make-serve": ["make serve", "make dev", "make run", "make watch", "make develop"],
    "just": ["just dev", "just serve", "just run"],
    "task": ["task dev", "task serve"],

    # === Frameworks ===
    "rails": [
        "rails server", "rails s",
        "bundle exec rails s", "bundle exec rails server",
    ],
    "ruby-servers": [
        "bundle exec puma -C config/puma.rb",
        "bundle exec unicorn",
        "puma",
        "thin start",
        "jekyll serve",
        "middleman server",
    ],
    "elixir": ["mix phx.server", "iex -S mix phx.server", "iex -S mix"],
    "static-site-serve": [
        "hugo server", "hugo serve -D",
        "mkdocs serve", "mkdocs serve -a 0.0.0.0:8000",
        "mdbook serve", "zola serve",
    ],
    "cloud-dev": [
        "wrangler dev",
        "firebase serve", "firebase emulators:start",
        "netlify dev",
        "vercel dev",
        "expo start", "expo start --tunnel",
    ],
    "misc-frameworks": [
        "meteor", "meteor run", "sails lift",
        "deno task dev",
        "bun run dev", "bun start",
        "astro dev",
    ],

    # === npm/yarn/pnpm/bun ===
    "npm-dev-start": [
        "npm start", "npm run dev", "npm run start",
        "npm run serve", "npm run watch",
        "yarn start", "yarn dev",
        "pnpm dev", "pnpm serve",
        "bun start",
    ],

    # === Watchers ===
    "watchers": [
        "nodemon", "nodemon app.js",
        "air", "air -c .air.toml",
        "cargo watch -x run", "cargo-watch -x run",
        "tsc --watch", "tsc -w",
        "rollup -w", "rollup --watch",
        "esbuild --watch", "webpack --watch", "webpack -w",
        "parcel --watch", "swc --watch",
        "watchman", "entr",
    ],
    "node-watch": ["node --watch app.js"],

    # === Server scripts by filename ===
    "server-scripts": [
        "python server.py", "python3 server.py",
        "python my_server.py", "python apps/server.py",
        "node server.js", "node my-server.mjs",
        "ruby server.rb",
        "deno run --allow-net server.ts",
    ],

    # === Process supervisors (foreground) ===
    "supervisors": [
        "pm2 start app.js --no-daemon",
        "pm2 logs",
        "supervisord -n",
        "forever app.js",
    ],

    # === Network listeners / sniffers ===
    "listeners": [
        "nc -l 8080", "nc -lk 8080", "ncat -l 8080",
        "socat TCP-LISTEN:8080,fork -",
        "tcpdump -i any", "tshark -i any",
        "mitmproxy", "mitmdump",
    ],

    # === SSH / tunnels ===
    "ssh-forwards": [
        "ssh -L 8080:localhost:80 user@host",
        "ssh -N -L 8080:localhost:80 user@host",
        "ssh -R 9000:localhost:22 user@host",
        "autossh -M 0 -N -L 8080:localhost:80 user@host",
    ],
    "tunnels": [
        "ngrok http 8080",
        "cloudflared tunnel run",
        "bore local 8080",
        "frpc -c frpc.ini",
        "frps -c frps.ini",
    ],

    # === Python / Web servers ===
    "python-servers": [
        "uvicorn app:app --reload",
        "gunicorn myapp.wsgi:application",
        "hypercorn app:app",
        "daphne app:application",
        "granian app:app",
        "flask run --port 5000",
        "streamlit run app.py",
        "celery worker -A tasks",
        "celery -A tasks worker",
        "python manage.py runserver",
        "./manage.py runserver 0.0.0.0:8000",
        "python3 manage.py runserver",
    ],

    # === Ad-hoc HTTP servers ===
    "adhoc-http": [
        "python -m http.server 8080",
        "python3 -m http.server",
        "python -m SimpleHTTPServer",
        "python -m RangeHTTPServer 8000",
        "php -S localhost:8000",
        "ruby -run -e httpd . -p 8000",
        "busybox httpd -f",
        "miniserve .",
        "simple-http-server",
        "devd",
    ],

    # === npx-launched servers ===
    "npx-servers": [
        "npx serve dist -l 4321",
        "npx serve dist -l 4321 --no-clipboard",
        "npx http-server . -p 8080",
        "npx live-server",
        "npx browser-sync start --server",
        "npx wrangler dev",
        "npx vite",
        "npx next dev",
        "npx nodemon",
    ],

    # === JS/TS dev servers ===
    "js-dev": [
        "next dev",
        "vite", "vite dev",
        "webpack-dev-server",
        "react-scripts start",
        "gatsby develop",
        "remix dev",
        "astro dev",
    ],

    # === Docker / k8s ===
    "docker-compose": [
        "docker compose up",
        "docker compose up --build",
        "docker-compose up",
    ],
    "docker-logs": [
        "docker compose logs -f",
        "docker logs -f container",
        "docker compose logs -f --tail=100",
    ],
    "docker-interactive": [
        "docker run -it ubuntu bash",
        "docker exec -it container bash",
    ],
    "kubectl": [
        "kubectl logs -f pod",
        "kubectl port-forward svc/web 8080:80",
        "kubectl exec -it pod -- bash",
        "kubectl proxy",
        "k9s",
        "stern .",
        "minikube tunnel",
        "minikube dashboard",
        "skaffold dev",
        "tilt up",
    ],

    # === Tail / journalctl / watch ===
    "tail-journalctl-watch": [
        "tail -f /var/log/syslog",
        "tail -F /var/log/app.log",
        "tail -fn 100 log.txt",
        "journalctl -fu hermes-gateway",
        "journalctl -f",
        "journalctl -u svc -f",
        "watch ls -la",
        "watch -n 1 free",
    ],

    # === Web servers ===
    "webservers": [
        "caddy run", "caddy reverse-proxy --to localhost:3000",
        "caddy file-server",
        "nginx start",
        "traefik start",
    ],

    # === REPLs (bare) ===
    "repls": [
        "python", "python3", "ipython", "bpython",
        "node",
        "irb", "pry",
        "ghci", "sbcl", "clisp",
        "scala", "kotlinc",
        "R", "julia", "lua",
    ],

    # === Database CLIs ===
    "db-cli": [
        "psql -U postgres",
        "psql -h localhost -U user dbname",
        "mysql -u root -p",
        "redis-cli",
        "mongosh",
        "sqlite3 /tmp/x.db",
        "cqlsh",
    ],

    # === TUIs ===
    "tuis": [
        "htop", "btop", "atop",
        "glances", "iotop", "iftop", "nethogs",
        "top",
        "cd /tmp && top",
        "ls; top",
    ],

    # === ML dashboards ===
    "ml-dashboards": [
        "tensorboard --logdir=runs",
        "jupyter notebook", "jupyter lab", "jupyter-lab",
        "jupyter notebook --port 8888",
        "mlflow ui", "mlflow server",
        "ray start",
        "ray dashboard",
        "wandb local",
    ],

    # === Pagers ===
    "pagers": [
        "less /var/log/syslog",
        "more /var/log/syslog",
        "most file.txt",
    ],

    # === Trace / profile ===
    "trace": [
        "strace -p 1234",
        "ltrace -p 1234",
        "perf top",
        "bpftrace foo.bt",
    ],

    # === Wrapper-prefixed long-running commands ===
    "wrapped-time": ["time python -m http.server"],
    "wrapped-nice": ["nice -n 10 python -m http.server"],
    "wrapped-env": [
        "env DEBUG=1 python -m http.server",
        "DEBUG=1 python -m http.server",
        "DEBUG=1 PORT=8080 python -m http.server",
    ],
    "wrapped-sudo": [
        "sudo python -m http.server 80",
        "sudo -E python -m http.server",
    ],
    "wrapped-shell-c": [
        "bash -c 'python -m http.server'",
        "sh -c 'python -m http.server 8080'",
        'bash -c "python -m http.server"',
    ],
    "wrapped-buffer": [
        "unbuffer python -m http.server",
        "stdbuf -oL python -m http.server",
    ],
    "wrapped-parens": [
        "(cd /tmp && python -m http.server 8080)",
    ],

    # === Shell `&` backgrounding (THE h2h hang case) ===
    "shell-backgrounding": [
        "python -m http.server 8080 &>/dev/null &",
        "npx serve dist -l 4321 &>/dev/null &",
        "node app.js & sleep 2 && curl localhost:3000",
        "(python -m http.server &) ; sleep 1 ; curl localhost:8000",
        "./long_running_thing.sh &",
        "myserver & disown",
    ],

    # === Explicit backgrounding ===
    "nohup-disown": [
        "nohup python app.py",
        "nohup ./script.sh",
        "myserver & disown",
    ],
}


# ─── SHOULD NOT AUTO-BACKGROUND (false-positive guards) ───────────────────

SHOULD_NOT_MATCH = {
    "quoted-strings": [
        # Long-running command names quoted inside an argument MUST NOT match
        "git commit -m 'add npx serve docs'",
        "echo 'starting python -m http.server'",
        "grep -r 'tail -f' .",
        "cat README.md | grep 'docker compose up'",
        'git commit -m "fix: nodemon docs"',
        "echo 'docker compose up'",
    ],
    "build-not-serve": [
        "npm install", "npm run build", "npm run test",
        "yarn install", "yarn build",
        "vite build", "vite preview", "vite optimize",
        "next build", "gatsby build",
        "make build", "make test", "make install",
        "docker compose up -d", "docker-compose up -d",
        "docker compose up --build -d",
        "cargo build", "cargo test",
    ],
    "git": [
        "git status", "git log --oneline",
        "git push origin main", "git pull",
        "git diff", "git checkout main",
    ],
    "shell-basic": [
        "ls", "ls -la", "df -h", "du -sh *",
        "pwd", "whoami",
        "echo hello", "echo 'hello world'",
        "rm -rf /tmp/foo",
        "find . -name '*.py'",
        "ps aux | grep python",
        "kill -9 1234",
        "true", "false",
    ],
    "test-runners": [
        "pytest", "pytest tests/",
        "go test ./...",
        "cargo test",
        "npm test",  # this is `test`, not `start`/`dev`
    ],
    "network-finite": [
        "curl https://example.com",
        "wget https://example.com/file.zip",
        "ping -c 4 google.com",
    ],
    "ambiguous-node": [
        # Bare `node script.js` — undecidable without reading the file.
        # Conservative: don't auto-background.  Agent should declare intent.
        "node index.js", "node app.js",
    ],
    "watch-in-text": [
        # "watch" not at command position
        "echo watching for changes",
    ],
}


# ─── PARAMETRIZE ──────────────────────────────────────────────────────────

_match_params = [
    pytest.param(cmd, id=f"{cat}::{cmd}")
    for cat, cmds in SHOULD_MATCH.items()
    for cmd in cmds
]

_no_match_params = [
    pytest.param(cmd, id=f"{cat}::{cmd}")
    for cat, cmds in SHOULD_NOT_MATCH.items()
    for cmd in cmds
]


@pytest.mark.parametrize("cmd", _match_params)
def test_should_auto_background(fn, cmd):
    """All these commands MUST be auto-backgrounded — they hang the agent."""
    assert fn(cmd), f"Expected auto-background for: {cmd!r}"


@pytest.mark.parametrize("cmd", _no_match_params)
def test_should_not_auto_background(fn, cmd):
    """All these commands MUST run in foreground — auto-background would be wrong."""
    assert not fn(cmd), f"Should NOT auto-background: {cmd!r}"


# ─── EDGE CASES ───────────────────────────────────────────────────────────

class TestEdgeCases:
    def test_empty_string(self, fn):
        assert not fn("")

    def test_whitespace_only(self, fn):
        assert not fn("   \n  \t  ")

    def test_logical_and_not_backgrounded(self, fn):
        # `&&` is logical AND, not backgrounding — must not trigger
        assert not fn("echo a && echo b")

    def test_redirect_amp_not_backgrounded(self, fn):
        # `&>` is a stderr/stdout redirect, not backgrounding
        assert not fn("ls &>/dev/null")

    def test_bare_amp_triggers_background(self, fn):
        # The h2h trap: bare `&` means user is detaching → auto-bg
        assert fn("./script.sh &")

    def test_double_quoted_inner_match(self, fn):
        # `bash -c "..."` with double quotes
        assert fn('bash -c "python -m http.server"')

    def test_nested_sudo_env(self, fn):
        # Multiple wrappers stacked
        assert fn("sudo -E env DEBUG=1 python -m http.server")


# ─── CONFIG TOGGLE ────────────────────────────────────────────────────────

class TestAutoBackgroundToggle:
    """Verify the TERMINAL_AUTO_BACKGROUND env-var toggle semantics.

    The actual gate is in terminal_tool.terminal_tool() — these tests just
    confirm the env-var parsing logic the runtime relies on.
    """

    def _enabled(self):
        return os.getenv("TERMINAL_AUTO_BACKGROUND", "true").lower() not in ("false", "0", "no")

    def test_enabled_by_default(self, monkeypatch):
        monkeypatch.delenv("TERMINAL_AUTO_BACKGROUND", raising=False)
        assert self._enabled()

    def test_disabled_via_env(self, monkeypatch):
        monkeypatch.setenv("TERMINAL_AUTO_BACKGROUND", "false")
        assert not self._enabled()

    def test_enabled_explicit(self, monkeypatch):
        monkeypatch.setenv("TERMINAL_AUTO_BACKGROUND", "true")
        assert self._enabled()

    @pytest.mark.parametrize("val", ["false", "0", "no", "FALSE", "No"])
    def test_disabled_variants(self, monkeypatch, val):
        monkeypatch.setenv("TERMINAL_AUTO_BACKGROUND", val)
        assert not self._enabled()
