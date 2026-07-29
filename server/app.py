from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import secrets
import subprocess
import threading
import time
import uuid
from dataclasses import dataclass
from functools import wraps
from pathlib import Path
from typing import Any, Callable
from urllib.parse import quote, urlsplit

import jwt
from bs4 import BeautifulSoup
from flask import Flask, Response, current_app, g, jsonify, redirect, render_template, request, session
from werkzeug.middleware.proxy_fix import ProxyFix

APP_NAME = "reunion"
URL_PREFIX = "/reunion"
DEFAULT_PORT = 13041
MAX_DOCUMENT_BYTES = 1_000_000
MAX_PROMPT_CHARS = 20_000
MAX_CODEX_OUTPUT_CHARS = 120_000
REQUIRED_IDS = {
    "rsvp",
    "rsvp-builder",
    "liveRsvpPending",
    "liveRsvpReady",
    "liveRsvpLink",
    "formBlueprint",
    "rsvpOutput",
    "rsvpStatus",
    "emailRsvp",
}
DANGEROUS_TAGS = {"script", "style", "iframe", "object", "embed", "base", "meta", "link"}
DANGEROUS_URL_SCHEMES = ("javascript:", "data:", "vbscript:")
SAFE_INLINE_HANDLERS = {"buildRsvp()", "copyRsvp()", "shareRsvp()", "copyBlueprint()"}


@dataclass(frozen=True)
class AuthenticatedUser:
    canonical_username: str
    mapped_username: str | None
    display_name: str | None = None

    @property
    def actor(self) -> str:
        return self.mapped_username or self.canonical_username


def parse_csv(value: str | None) -> set[str]:
    return {item.strip().lower() for item in (value or "").split(",") if item.strip()}


def truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


def create_app(test_config: dict[str, Any] | None = None) -> Flask:
    repo_root = Path(os.environ.get("REUNION_REPO_ROOT") or Path(__file__).resolve().parents[1]).expanduser().resolve()
    data_root = Path(os.environ.get("REUNION_DATA_ROOT", "/home/ubuntu/webapps_data/reunion")).expanduser().resolve()
    sso_secret = (os.environ.get("SSO_JWT_SECRET") or "").strip()
    auth_disabled = truthy(os.environ.get("REUNION_AUTH_DISABLED"))
    if not auth_disabled and len(sso_secret) < 32:
        raise RuntimeError("SSO_JWT_SECRET must be configured and at least 32 characters")

    session_secret = (os.environ.get("REUNION_SECRET_KEY") or "").strip()
    if not session_secret:
        session_secret = hashlib.sha256(f"reunion-session:{sso_secret or 'local-dev'}".encode()).hexdigest()

    app = Flask(__name__, template_folder=str(Path(__file__).resolve().parent / "templates"))
    app.config.update(
        SECRET_KEY=session_secret,
        URL_PREFIX=URL_PREFIX,
        REPO_ROOT=repo_root,
        DATA_ROOT=data_root,
        INDEX_PATH=repo_root / "index.html",
        AUTH_DISABLED=auth_disabled,
        JWT_SECRET=sso_secret,
        SSO_BASE_URL=(os.environ.get("SSO_BASE_URL") or "https://taylorarchibald.com").rstrip("/"),
        ADMIN_USERS=parse_csv(os.environ.get("REUNION_ADMIN_USERS", "tahlor,tahlor@gmail.com")),
        CODEX_RUNNER=(os.environ.get("REUNION_CODEX_RUNNER") or "").strip(),
        CODEX_TIMEOUT_SECONDS=int(os.environ.get("REUNION_CODEX_TIMEOUT_SECONDS", "1800")),
        RSVP_RESULTS_URL=(os.environ.get("REUNION_RSVP_RESULTS_URL") or "").strip(),
        PUBLISH_SCRIPT=str(repo_root / "deploy" / "publish.sh"),
        SESSION_COOKIE_NAME="reunion_admin_session",
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SECURE=not auth_disabled,
        SESSION_COOKIE_SAMESITE="Lax",
        MAX_CONTENT_LENGTH=MAX_DOCUMENT_BYTES + 100_000,
    )
    if test_config:
        app.config.update(test_config)

    @app.after_request
    def _admin_cache_headers(response: Response) -> Response:
        if request.path.startswith(f"{URL_PREFIX}/admin") or request.path.startswith(f"{URL_PREFIX}/edit") or request.path.startswith(f"{URL_PREFIX}/api/"):
            response.headers["Cache-Control"] = "no-store, max-age=0"
            response.headers["Pragma"] = "no-cache"
            response.headers["X-Content-Type-Options"] = "nosniff"
            response.headers["Referrer-Policy"] = "same-origin"
        return response

    data_root.mkdir(parents=True, exist_ok=True)
    (data_root / "backups").mkdir(parents=True, exist_ok=True)
    (data_root / "codex").mkdir(parents=True, exist_ok=True)
    initialize_turn_store(data_root / "codex" / "turns.json")

    app.before_request(load_authenticated_user)
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)
    register_routes(app)
    return app


def register_routes(app: Flask) -> None:
    @app.get(f"{URL_PREFIX}/health")
    def health() -> Response:
        return jsonify({"ok": True, "app": APP_NAME, "version": "2026-07-29"})

    @app.get(f"{URL_PREFIX}/sso/login")
    def sso_login_redirect() -> Response:
        return_url = request.args.get("return_url") or external_url()
        return redirect(f"{current_app.config['SSO_BASE_URL']}/sso/login?return_url={quote(return_url, safe='')}")

    @app.get(f"{URL_PREFIX}/edit")
    @require_admin
    def edit_page() -> str:
        return render_template(
            "edit.html",
            csrf_token=ensure_csrf_token(),
            actor=g.reunion_user.actor,
            url_prefix=URL_PREFIX,
        )

    @app.get(f"{URL_PREFIX}/admin")
    @require_admin
    def admin_page() -> str:
        return render_template(
            "admin.html",
            csrf_token=ensure_csrf_token(),
            actor=g.reunion_user.actor,
            url_prefix=URL_PREFIX,
        )

    @app.get(f"{URL_PREFIX}/api/me")
    @require_admin
    def api_me() -> Response:
        return jsonify({"ok": True, "user": g.reunion_user.actor, "canonical": g.reunion_user.canonical_username})

    @app.get(f"{URL_PREFIX}/api/rsvp")
    @require_admin
    def rsvp_api() -> Response:
        return jsonify({
            "form_url": public_rsvp_url(),
            "results_url": private_rsvp_results_url(),
        })

    @app.get(f"{URL_PREFIX}/api/document")
    @require_admin
    def get_document() -> Response:
        document = read_document()
        fragment = extract_main_html(document)
        return jsonify({
            "html": fragment,
            "revision": revision_for(fragment),
            "updated_at": int(current_app.config["INDEX_PATH"].stat().st_mtime),
        })

    @app.post(f"{URL_PREFIX}/api/document")
    @require_admin
    @require_csrf
    def save_document() -> Response:
        payload = request.get_json(silent=True) or {}
        fragment = str(payload.get("html") or "")
        expected_revision = str(payload.get("revision") or "")
        note = str(payload.get("note") or "").strip()[:180]
        if not fragment:
            return jsonify({"error": "Document content is required."}), 400
        if len(fragment.encode("utf-8")) > MAX_DOCUMENT_BYTES:
            return jsonify({"error": "Document is too large."}), 413

        index_path = Path(current_app.config["INDEX_PATH"])
        with document_lock():
            original_document = read_document()
            original_fragment = extract_main_html(original_document)
            current_revision = revision_for(original_fragment)
            if not hmac.compare_digest(expected_revision, current_revision):
                return jsonify({"error": "The page changed after you opened it. Reload before publishing.", "revision": current_revision}), 409

            try:
                cleaned_fragment = clean_and_validate_fragment(fragment)
            except ValueError as exc:
                return jsonify({"error": str(exc)}), 400

            if revision_for(cleaned_fragment) == current_revision:
                return jsonify({"ok": True, "unchanged": True, "revision": current_revision})

            try:
                head_before = ensure_clean_worktree()
            except RuntimeError as exc:
                return jsonify({"error": str(exc)}), 409

            new_document = replace_main_html(original_document, cleaned_fragment)
            backup_path = write_backup(original_document)
            atomic_write(index_path, new_document)
            audit_event("document_saved", g.reunion_user.actor, {
                "old_revision": current_revision,
                "new_revision": revision_for(cleaned_fragment),
                "backup": str(backup_path),
                "note": note,
            })

            try:
                publish_result = run_publish_script(g.reunion_user.actor, note)
            except RuntimeError as exc:
                restored = False
                try:
                    if git_head() == head_before:
                        atomic_write(index_path, original_document)
                        restored = True
                except RuntimeError:
                    restored = False
                audit_event("publish_failed", g.reunion_user.actor, {"error": str(exc), "backup": str(backup_path), "restored": restored})
                return jsonify({
                    "error": "Publish failed; the previous page was restored." if restored else "Publish failed after Git created a commit; the Archimedes agent must finish or roll back the commit.",
                    "details": str(exc),
                    "backup": str(backup_path),
                }), 500

            new_revision = revision_for(cleaned_fragment)
            audit_event("document_published", g.reunion_user.actor, {
                "revision": new_revision,
                "publish_output": publish_result[-4000:],
            })
            return jsonify({"ok": True, "revision": new_revision, "publish_output": publish_result[-4000:]})

    @app.get(f"{URL_PREFIX}/api/history")
    @require_admin
    def history_api() -> Response:
        return jsonify({"events": read_audit_events(limit=50)})

    @app.get(f"{URL_PREFIX}/api/codex/status")
    @require_admin
    def codex_status_api() -> Response:
        runner = configured_codex_runner()
        return jsonify({
            "configured": bool(runner),
            "runner": str(runner) if runner else None,
            "busy": codex_is_busy(),
        })

    @app.get(f"{URL_PREFIX}/api/codex/turns")
    @require_admin
    def codex_turns_api() -> Response:
        return jsonify({"turns": read_turns()})

    @app.post(f"{URL_PREFIX}/api/codex/turns")
    @require_admin
    @require_csrf
    def create_codex_turn_api() -> Response:
        payload = request.get_json(silent=True) or {}
        prompt = str(payload.get("prompt") or "").strip()
        if not prompt:
            return jsonify({"error": "Message is required."}), 400
        if len(prompt) > MAX_PROMPT_CHARS:
            return jsonify({"error": f"Message must be under {MAX_PROMPT_CHARS:,} characters."}), 400
        runner = configured_codex_runner()
        if not runner:
            return jsonify({"error": "The Codex runner has not been configured on Archimedes yet."}), 503
        if codex_is_busy():
            return jsonify({"error": "A Codex turn is already running. Wait for it to finish."}), 409

        turn = {
            "id": uuid.uuid4().hex,
            "actor": g.reunion_user.actor,
            "prompt": prompt,
            "status": "queued",
            "created_at": int(time.time()),
            "started_at": None,
            "completed_at": None,
            "response": "",
            "error": "",
        }
        append_turn(turn)
        app_object = current_app._get_current_object()
        thread = threading.Thread(target=run_codex_turn, args=(app_object, turn["id"], prompt, g.reunion_user.actor), daemon=True)
        thread.start()
        return jsonify({"ok": True, "turn": turn}), 202


def load_authenticated_user() -> None:
    if current_app.config.get("AUTH_DISABLED"):
        g.reunion_user = AuthenticatedUser("local-dev", "local-dev", "Local development")
        return
    token = request.cookies.get("universal_sso_token")
    if not token:
        g.reunion_user = None
        return
    try:
        decoded = jwt.decode(token, current_app.config["JWT_SECRET"], algorithms=["HS256"])
    except jwt.PyJWTError:
        g.reunion_user = None
        return
    canonical = str(decoded.get("sub") or "").strip()
    mappings = decoded.get("mappings") if isinstance(decoded.get("mappings"), dict) else {}
    mapped = str(mappings.get(APP_NAME) or "").strip() or None
    if not canonical:
        g.reunion_user = None
        return
    g.reunion_user = AuthenticatedUser(canonical, mapped, decoded.get("name"))


def is_authorized(user: AuthenticatedUser) -> bool:
    admins = current_app.config["ADMIN_USERS"]
    return user.canonical_username.lower() in admins or (user.mapped_username or "").lower() in admins


def require_admin(view_func: Callable[..., Any]) -> Callable[..., Any]:
    @wraps(view_func)
    def wrapped(*args: Any, **kwargs: Any) -> Any:
        user = getattr(g, "reunion_user", None)
        if user is None:
            return redirect(f"{URL_PREFIX}/sso/login?return_url={quote(external_url(), safe='')}")
        if not is_authorized(user):
            return jsonify({"error": "This SSO account is not authorized to administer the reunion site."}), 403
        return view_func(*args, **kwargs)

    return wrapped


def ensure_csrf_token() -> str:
    token = session.get("csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        session["csrf_token"] = token
    return str(token)


def require_csrf(view_func: Callable[..., Any]) -> Callable[..., Any]:
    @wraps(view_func)
    def wrapped(*args: Any, **kwargs: Any) -> Any:
        expected = str(session.get("csrf_token") or "")
        provided = str(request.headers.get("X-CSRF-Token") or "")
        if not expected or not provided or not hmac.compare_digest(expected, provided):
            return jsonify({"error": "Invalid CSRF token."}), 403
        origin = request.headers.get("Origin")
        if origin:
            origin_parts = urlsplit(origin)
            expected_host = (request.headers.get("X-Forwarded-Host") or request.host).split(",", 1)[0].strip()
            if origin_parts.netloc != expected_host:
                return jsonify({"error": "Cross-origin request blocked."}), 403
        return view_func(*args, **kwargs)

    return wrapped


def external_url() -> str:
    proto = (request.headers.get("X-Forwarded-Proto") or request.scheme).split(",", 1)[0].strip()
    host = (request.headers.get("X-Forwarded-Host") or request.host).split(",", 1)[0].strip()
    if proto == "http" and host.endswith("taylorarchibald.com"):
        proto = "https"
    path = request.full_path[:-1] if request.full_path.endswith("?") else request.full_path
    return f"{proto}://{host}{path}"


def read_document() -> str:
    path = Path(current_app.config["INDEX_PATH"])
    if not path.is_file():
        raise RuntimeError(f"Missing reunion document: {path}")
    return path.read_text(encoding="utf-8")


def safe_external_link(value: str) -> str | None:
    parsed = urlsplit(value.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    return value.strip()


def public_rsvp_url() -> str | None:
    config_path = Path(current_app.config["REPO_ROOT"]) / "config.js"
    if not config_path.is_file():
        return None
    match = re.search(r"rsvpFormUrl\s*:\s*(['\"])(.*?)\1", config_path.read_text(encoding="utf-8"))
    return safe_external_link(match.group(2)) if match else None


def private_rsvp_results_url() -> str | None:
    return safe_external_link(str(current_app.config.get("RSVP_RESULTS_URL") or ""))


def main_bounds(document: str) -> tuple[int, int]:
    opening = re.search(r"<main\b[^>]*>", document, flags=re.IGNORECASE)
    if not opening:
        raise RuntimeError("index.html does not contain a <main> element")
    closing_start = document.lower().rfind("</main>")
    if closing_start < opening.end():
        raise RuntimeError("index.html does not contain a valid closing </main>")
    return opening.end(), closing_start


def extract_main_html(document: str) -> str:
    start, end = main_bounds(document)
    return document[start:end]


def replace_main_html(document: str, fragment: str) -> str:
    start, end = main_bounds(document)
    return document[:start] + fragment + document[end:]


def revision_for(fragment: str) -> str:
    return hashlib.sha256(fragment.encode("utf-8")).hexdigest()


def clean_and_validate_fragment(fragment: str) -> str:
    soup = BeautifulSoup(fragment, "html.parser")
    for tag in soup.find_all(True):
        name = (tag.name or "").lower()
        if name in DANGEROUS_TAGS:
            raise ValueError(f"The editor cannot publish <{name}> elements.")
        for attribute, raw_value in list(tag.attrs.items()):
            attr = attribute.lower()
            values = raw_value if isinstance(raw_value, list) else [raw_value]
            if attr.startswith("on"):
                handler = str(raw_value or "").strip()
                if not (attr == "onclick" and name == "button" and handler in SAFE_INLINE_HANDLERS):
                    raise ValueError(f"Unsafe attribute '{attribute}' is not allowed.")
            if attr in {"srcdoc", "formaction"}:
                raise ValueError(f"Unsafe attribute '{attribute}' is not allowed.")
            if attr in {"href", "src", "action"}:
                for value in values:
                    normalized = str(value or "").strip().lower()
                    if normalized.startswith(DANGEROUS_URL_SCHEMES):
                        raise ValueError("Unsafe URL scheme is not allowed.")
            if attr == "contenteditable" or attr.startswith("data-reunion-editor"):
                del tag.attrs[attribute]
        classes = tag.get("class")
        if classes:
            tag["class"] = [item for item in classes if item not in {"reunion-editor-selected", "reunion-editor-hover"}]
            if not tag["class"]:
                del tag["class"]

    ids = {str(tag.get("id")) for tag in soup.find_all(attrs={"id": True})}
    missing = sorted(REQUIRED_IDS - ids)
    if missing:
        raise ValueError("The edit removed required page controls: " + ", ".join(missing))

    plain_text = soup.get_text(" ", strip=True)
    if "Hazard Family Reunion" not in plain_text:
        raise ValueError("The page must retain the Hazard Family Reunion title.")
    lowered = plain_text.lower()
    if "archibald family reunion" in lowered or "casey and morgan reunion" in lowered:
        raise ValueError("Incorrect reunion branding was detected.")

    cleaned = str(soup)
    return "\n" + cleaned.strip() + "\n"


def atomic_write(path: Path, content: str) -> None:
    temp = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    temp.write_text(content, encoding="utf-8")
    os.replace(temp, path)


def write_backup(document: str) -> Path:
    backup_root = Path(current_app.config["DATA_ROOT"]) / "backups"
    stamp = time.strftime("%Y%m%d-%H%M%S", time.gmtime())
    backup_path = backup_root / f"index-{stamp}-{uuid.uuid4().hex[:8]}.html"
    backup_path.write_text(document, encoding="utf-8")
    return backup_path


def git_command(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        ["git", *args],
        cwd=str(current_app.config["REPO_ROOT"]),
        text=True,
        capture_output=True,
        check=False,
        timeout=30,
    )
    if check and result.returncode != 0:
        raise RuntimeError((result.stdout or "") + (result.stderr or "") or f"git {' '.join(args)} failed")
    return result


def git_head() -> str:
    return git_command("rev-parse", "HEAD").stdout.strip()


def ensure_clean_worktree() -> str:
    status = git_command("status", "--porcelain").stdout.strip()
    if status:
        raise RuntimeError("The Archimedes reunion checkout has uncommitted changes. Resolve them before publishing from the editor.")
    return git_head()


def run_publish_script(actor: str, note: str) -> str:
    script = Path(current_app.config["PUBLISH_SCRIPT"])
    if not script.is_file():
        raise RuntimeError(f"Publish script is missing: {script}")
    env = os.environ.copy()
    env["REUNION_PUBLISH_ACTOR"] = actor
    env["REUNION_PUBLISH_NOTE"] = note
    result = subprocess.run(
        ["bash", str(script)],
        cwd=str(current_app.config["REPO_ROOT"]),
        env=env,
        text=True,
        capture_output=True,
        timeout=180,
        check=False,
    )
    output = (result.stdout or "") + (result.stderr or "")
    if result.returncode != 0:
        raise RuntimeError(output.strip()[-8000:] or f"publish.sh exited {result.returncode}")
    return output.strip()


def audit_path() -> Path:
    return Path(current_app.config["DATA_ROOT"]) / "audit.jsonl"


def audit_event(event: str, actor: str, details: dict[str, Any]) -> None:
    row = {"timestamp": int(time.time()), "event": event, "actor": actor, "details": details}
    with audit_path().open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def read_audit_events(limit: int) -> list[dict[str, Any]]:
    path = audit_path()
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines()[-limit:]:
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return list(reversed(rows))


_DOCUMENT_LOCK = threading.Lock()
_CODEX_LOCK = threading.Lock()
_TURN_STORE_LOCK = threading.Lock()


def document_lock() -> threading.Lock:
    return _DOCUMENT_LOCK


def turns_path() -> Path:
    return Path(current_app.config["DATA_ROOT"]) / "codex" / "turns.json"


def initialize_turn_store(path: Path) -> None:
    if not path.exists():
        path.write_text("[]\n", encoding="utf-8")
        return
    try:
        turns = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        turns = []
    changed = False
    for turn in turns:
        if turn.get("status") in {"queued", "running"}:
            turn["status"] = "interrupted"
            turn["completed_at"] = int(time.time())
            turn["error"] = "The reunion admin service restarted before this turn completed."
            changed = True
    if changed:
        path.write_text(json.dumps(turns, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def read_turns() -> list[dict[str, Any]]:
    with _TURN_STORE_LOCK:
        path = turns_path()
        try:
            turns = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return []
    return turns[-100:]


def write_turns(turns: list[dict[str, Any]]) -> None:
    path = turns_path()
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(turns, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(temp, path)


def append_turn(turn: dict[str, Any]) -> None:
    with _TURN_STORE_LOCK:
        try:
            turns = json.loads(turns_path().read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            turns = []
        turns.append(turn)
        write_turns(turns)


def update_turn(turn_id: str, **updates: Any) -> None:
    with _TURN_STORE_LOCK:
        try:
            turns = json.loads(turns_path().read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            turns = []
        for turn in turns:
            if turn.get("id") == turn_id:
                turn.update(updates)
                break
        write_turns(turns)


def codex_is_busy() -> bool:
    return any(turn.get("status") in {"queued", "running"} for turn in read_turns())


def configured_codex_runner() -> Path | None:
    value = str(current_app.config.get("CODEX_RUNNER") or "").strip()
    if not value:
        return None
    path = Path(value).expanduser().resolve()
    return path if path.is_file() and os.access(path, os.X_OK) else None


def run_codex_turn(app: Flask, turn_id: str, prompt: str, actor: str) -> None:
    with app.app_context():
        with _CODEX_LOCK:
            runner = configured_codex_runner()
            if not runner:
                update_turn(turn_id, status="failed", completed_at=int(time.time()), error="Codex runner is not configured.")
                return
            update_turn(turn_id, status="running", started_at=int(time.time()))
            env = os.environ.copy()
            env.update({
                "REUNION_REPO_ROOT": str(current_app.config["REPO_ROOT"]),
                "REUNION_CODEX_SESSION_DIR": str(Path(current_app.config["DATA_ROOT"]) / "codex" / "session"),
                "REUNION_CODEX_ACTOR": actor,
            })
            Path(env["REUNION_CODEX_SESSION_DIR"]).mkdir(parents=True, exist_ok=True)
            try:
                result = subprocess.run(
                    [str(runner)],
                    cwd=str(current_app.config["REPO_ROOT"]),
                    env=env,
                    input=prompt,
                    text=True,
                    capture_output=True,
                    timeout=int(current_app.config["CODEX_TIMEOUT_SECONDS"]),
                    check=False,
                )
                stdout = (result.stdout or "")[-MAX_CODEX_OUTPUT_CHARS:]
                stderr = (result.stderr or "")[-20_000:]
                if result.returncode == 0:
                    update_turn(turn_id, status="completed", completed_at=int(time.time()), response=stdout.strip(), error=stderr.strip())
                    audit_event("codex_turn_completed", actor, {"turn_id": turn_id})
                else:
                    update_turn(turn_id, status="failed", completed_at=int(time.time()), response=stdout.strip(), error=(stderr or stdout).strip())
                    audit_event("codex_turn_failed", actor, {"turn_id": turn_id, "returncode": result.returncode})
            except subprocess.TimeoutExpired:
                update_turn(turn_id, status="failed", completed_at=int(time.time()), error="Codex turn timed out.")
                audit_event("codex_turn_timeout", actor, {"turn_id": turn_id})
            except OSError as exc:
                update_turn(turn_id, status="failed", completed_at=int(time.time()), error=str(exc))
                audit_event("codex_turn_failed", actor, {"turn_id": turn_id, "error": str(exc)})


if __name__ == "__main__":
    from waitress import serve

    serve(create_app(), host="127.0.0.1", port=int(os.environ.get("PORT", DEFAULT_PORT)))
