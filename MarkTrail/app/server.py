from __future__ import annotations

import json
import mimetypes
import os
import re
import threading
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from http import cookies
from pathlib import Path
from urllib.parse import urlparse

from .auth import clear_session_cookie, current_user, login, session_cookie, SESSION_COOKIE
from .chain import ChainClient
from .db import Database
from .service import AppError, AppService


ROOT = Path(__file__).resolve().parents[1]
WEB_DIR = ROOT / "web"

# ---------------------------------------------------------------------------
# Login rate limiter: 10 failures per IP per 15-minute window → HTTP 429
# ---------------------------------------------------------------------------
_rate_lock = threading.Lock()
_failed_attempts: dict[str, list[float]] = {}
_RATE_WINDOW = 900   # seconds (15 min)
_MAX_FAILURES = 10


def _client_ip(handler: BaseHTTPRequestHandler) -> str:
    forwarded = handler.headers.get("X-Forwarded-For", "")
    return forwarded.split(",")[0].strip() or handler.client_address[0]


def _is_rate_limited(ip: str) -> bool:
    now = time.monotonic()
    with _rate_lock:
        window = [t for t in _failed_attempts.get(ip, []) if now - t < _RATE_WINDOW]
        _failed_attempts[ip] = window
        return len(window) >= _MAX_FAILURES


def _record_failure(ip: str) -> None:
    now = time.monotonic()
    with _rate_lock:
        _failed_attempts.setdefault(ip, []).append(now)


def _clear_failures(ip: str) -> None:
    with _rate_lock:
        _failed_attempts.pop(ip, None)


class MarkTrailHandler(BaseHTTPRequestHandler):
    server_version = "MarkTrail/1.0"

    @property
    def db(self) -> Database:
        return self.server.db  # type: ignore[attr-defined]

    @property
    def service(self) -> AppService:
        return self.server.service  # type: ignore[attr-defined]

    def _send_json(self, payload, status: int = 200, extra_headers: dict | None = None):
        body = json.dumps(payload, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for key, value in (extra_headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)

    def _send_text(self, text: str, status: int = 200, content_type: str = "text/plain"):
        body = text.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type + "; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        if self.path.startswith("/api/"):
            self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _body(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        if length > 2_000_000:
            raise AppError("Request body is too large.", 413)
        raw = self.rfile.read(length)
        if not raw:
            return {}
        try:
            return json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise AppError("Request body must be valid JSON.", 400) from exc

    def _user(self):
        return current_user(self.db, self.headers.get("Cookie"))

    def _require_user(self):
        user = self._user()
        if not user:
            raise AppError("Authentication required.", 401)
        return user

    def _dispatch(self, method: str):
        parsed = urlparse(self.path)
        path = parsed.path

        if method == "GET" and not path.startswith("/api/"):
            return self._serve_static(path)

        if method == "GET" and path == "/api/health":
            return self._send_json({"ok": True, "service": "MarkTrail"})

        if method == "POST" and path == "/api/login":
            ip = _client_ip(self)
            if _is_rate_limited(ip):
                raise AppError(
                    "Too many failed login attempts. Please wait 15 minutes.", 429
                )
            body = self._body()
            result = login(
                self.db,
                str(body.get("username", "")),
                str(body.get("password", "")),
            )
            if not result:
                _record_failure(ip)
                raise AppError("Invalid username or password.", 401)
            session_id, must_change = result
            _clear_failures(ip)
            return self._send_json(
                {"ok": True, "must_change_password": must_change},
                200,
                {"Set-Cookie": session_cookie(session_id)},
            )

        if method == "POST" and path == "/api/logout":
            jar = cookies.SimpleCookie()
            jar.load(self.headers.get("Cookie", ""))
            morsel = jar.get(SESSION_COOKIE)
            if morsel:
                self.db.delete_session(morsel.value)
            return self._send_json(
                {"ok": True},
                200,
                {"Set-Cookie": clear_session_cookie()},
            )

        user = self._require_user()
        user_id = int(user["id"])

        if method == "GET" and path == "/api/me":
            return self._send_json(
                {
                    "user": {
                        k: user[k]
                        for k in ("id", "username", "full_name", "role")
                    },
                    "must_change_password": bool(user["must_change_password"]),
                }
            )

        # Force password change before any other action
        if user["must_change_password"] and path != "/api/auth/change-password":
            raise AppError(
                "You must change your password before continuing.", 403
            )

        if method == "POST" and path == "/api/auth/change-password":
            body = self._body()
            return self._send_json(
                self.service.change_password(
                    user_id,
                    str(body.get("current_password", "")),
                    str(body.get("new_password", "")),
                )
            )

        if method == "GET" and path == "/api/dashboard":
            return self._send_json(self.service.dashboard(user_id))

        if method == "GET" and path == "/api/status":
            return self._send_json({"chain": ChainClient().status()})

        if method == "GET" and path == "/api/student/marks":
            return self._send_json({"marks": self.service.student_marks(user_id)})

        match = re.fullmatch(r"/api/student/marks/([^/]+)", path)
        if method == "GET" and match:
            return self._send_json(
                self.service.student_mark_detail(user_id, match.group(1))
            )

        if method == "GET" and path == "/api/student/reports":
            return self._send_json({"reports": self.service.student_reports(user_id)})

        if method == "GET" and path == "/api/student/notifications":
            return self._send_json(
                {"notifications": self.service.student_notifications(user_id)}
            )

        match = re.fullmatch(r"/api/student/notifications/(\d+)/read", path)
        if method == "POST" and match:
            return self._send_json(
                self.service.mark_notification_read(user_id, int(match.group(1)))
            )

        if method == "POST" and path == "/api/student/reports":
            body = self._body()
            return self._send_json(
                self.service.report_missing_mark(
                    user_id,
                    str(body.get("assessment_id", "")),
                ),
                201,
            )

        if method == "GET" and path == "/api/lecturer/assessments":
            return self._send_json(
                {"assessments": self.service.lecturer_assessments(user_id)}
            )

        if method == "GET" and path == "/api/lecturer/batches":
            return self._send_json(
                {"batches": self.service.lecturer_batches(user_id)}
            )

        if method == "GET" and path == "/api/lecturer/reports":
            return self._send_json(
                {"reports": self.service.lecturer_reports(user_id)}
            )

        if method == "POST" and path == "/api/lecturer/batches/preview":
            body = self._body()
            return self._send_json(
                self.service.preview_batch(
                    user_id,
                    str(body.get("assessment_id", "")),
                    str(body.get("csv", "")),
                )
            )

        if method == "POST" and path == "/api/lecturer/batches/submit":
            body = self._body()
            return self._send_json(
                self.service.submit_batch(
                    user_id,
                    str(body.get("assessment_id", "")),
                    str(body.get("csv", "")),
                ),
                201,
            )

        match = re.fullmatch(r"/api/lecturer/reports/([^/]+)/reject", path)
        if method == "POST" and match:
            body = self._body()
            return self._send_json(
                self.service.reject_report(
                    user_id,
                    match.group(1),
                    str(body.get("reason", "")),
                )
            )

        match = re.fullmatch(r"/api/lecturer/reports/([^/]+)/resolve", path)
        if method == "POST" and match:
            body = self._body()
            raw_mark = body.get("mark")
            return self._send_json(
                self.service.resolve_report(
                    user_id,
                    match.group(1),
                    str(body.get("resolution_type", "")),
                    float(raw_mark) if raw_mark not in (None, "") else None,
                    str(body.get("note", "")),
                )
            )

        match = re.fullmatch(r"/api/lecturer/batches/(0x[a-fA-F0-9]{64})/retry-chain", path)
        if method == "POST" and match:
            return self._send_json(self.service.retry_chain(user_id, match.group(1)))

        if method == "GET" and path == "/api/reviewer/batches":
            return self._send_json(
                {"batches": self.service.reviewer_batches(user_id)}
            )

        if method == "GET" and path == "/api/exam-office/batches":
            return self._send_json(
                {"batches": self.service.exam_office_batches(user_id)}
            )

        match = re.fullmatch(r"/api/exam-office/batches/(0x[a-fA-F0-9]{64})/process", path)
        if method == "POST" and match:
            return self._send_json(
                self.service.process_exam_office_batch(user_id, match.group(1))
            )

        if method == "GET" and path == "/api/portal/batches":
            return self._send_json(
                {"batches": self.service.portal_batches(user_id)}
            )

        match = re.fullmatch(r"/api/portal/batches/(0x[a-fA-F0-9]{64})/publish", path)
        if method == "POST" and match:
            return self._send_json(
                self.service.publish_portal_batch(user_id, match.group(1))
            )

        match = re.fullmatch(r"/api/reviewer/batches/(0x[a-fA-F0-9]{64})/verify", path)
        if method == "POST" and match:
            return self._send_json(
                self.service.verify_batch(user_id, match.group(1))
            )

        match = re.fullmatch(r"/api/reviewer/batches/(0x[a-fA-F0-9]{64})/retry-chain", path)
        if method == "POST" and match:
            return self._send_json(self.service.retry_chain(user_id, match.group(1)))

        match = re.fullmatch(r"/api/admin/batches/(0x[a-fA-F0-9]{64})/retry-chain", path)
        if method == "POST" and match:
            return self._send_json(self.service.retry_chain(user_id, match.group(1)))

        if method == "POST" and path == "/api/admin/batches/recover":
            self.service.require_role(user_id, {"admin"})
            return self._send_json(self.service.recover_pending_batches())

        if method == "GET" and path == "/api/admin/batches":
            return self._send_json({"batches": self.service.admin_batches(user_id)})

        if method == "GET" and path == "/api/admin/users":
            return self._send_json({"users": self.service.admin_users(user_id)})

        if method == "GET" and path == "/api/admin/courses":
            return self._send_json({"courses": self.service.admin_courses(user_id)})

        if method == "POST" and path == "/api/admin/users":
            body = self._body()
            return self._send_json(
                self.service.admin_create_user(
                    user_id,
                    str(body.get("username", "")),
                    str(body.get("full_name", "")),
                    str(body.get("role", "")),
                    str(body.get("password", "")),
                    str(body.get("reg_number", "")) or None,
                    str(body.get("access_until", "")) or None,
                ),
                201,
            )

        match = re.fullmatch(r"/api/admin/users/(\d+)/access", path)
        if method == "POST" and match:
            body = self._body()
            return self._send_json(
                self.service.admin_update_user_access(
                    user_id,
                    int(match.group(1)),
                    body.get("active"),
                    str(body.get("access_until", "")) or None,
                )
            )

        match = re.fullmatch(r"/api/admin/courses/([^/]+)/bulk-enroll", path)
        if method == "POST" and match:
            body = self._body()
            return self._send_json(
                self.service.admin_bulk_enroll_csv(
                    user_id,
                    match.group(1),
                    str(body.get("csv", "")),
                    str(body.get("default_password", "ChangeMe123")),
                    str(body.get("access_until", "")) or None,
                )
            )

        if method == "POST" and path == "/api/admin/courses":
            body = self._body()
            try:
                lecturer_id = int(body.get("lecturer_id"))
            except (TypeError, ValueError) as exc:
                raise AppError("lecturer_id must be a valid user ID.") from exc

            return self._send_json(
                self.service.admin_create_course(
                    user_id,
                    str(body.get("code", "")),
                    str(body.get("title", "")),
                    lecturer_id,
                ),
                201,
            )

        match = re.fullmatch(r"/api/admin/courses/([^/]+)/enroll", path)
        if method == "POST" and match:
            body = self._body()
            try:
                ids = [int(value) for value in body.get("student_ids", [])]
            except (TypeError, ValueError) as exc:
                raise AppError("student_ids must be numeric user IDs.") from exc
            return self._send_json(
                self.service.admin_enroll(user_id, match.group(1), ids)
            )

        match = re.fullmatch(r"/api/admin/courses/([^/]+)/assessments", path)
        if method == "POST" and match:
            body = self._body()
            try:
                max_mark = float(body.get("max_mark"))
            except (TypeError, ValueError) as exc:
                raise AppError("max_mark must be numeric.") from exc
            return self._send_json(
                self.service.admin_create_assessment(
                    user_id,
                    match.group(1),
                    str(body.get("name", "")),
                    max_mark,
                    str(body.get("submission_deadline", "")) or None,
                ),
                201,
            )

        match = re.fullmatch(r"/api/audit/batch/(0x[a-fA-F0-9]{64})", path)
        if method == "GET" and match:
            return self._send_json(
                self.service.batch_audit(user_id, match.group(1))
            )

        match = re.fullmatch(
            r"/api/audit/batch/(0x[a-fA-F0-9]{64})/report\.csv",
            path,
        )
        if method == "GET" and match:
            body = self.service.batch_report_csv(user_id, match.group(1)).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/csv; charset=utf-8")
            self.send_header(
                "Content-Disposition",
                f'attachment; filename="marktrail-audit-{match.group(1)[2:14]}.csv"',
            )
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
            return

        match = re.fullmatch(r"/api/audit/batch/(0x[a-fA-F0-9]{64})/pipeline", path)
        if method == "GET" and match:
            return self._send_json(
                self.service.batch_pipeline(user_id, match.group(1))
            )

        match = re.fullmatch(r"/api/admin/reconcile/(0x[a-fA-F0-9]{64})", path)
        if method == "GET" and match:
            return self._send_json(
                self.service.reconcile_batch(user_id, match.group(1))
            )

        raise AppError("Not found.", 404)

    def _serve_static(self, path: str):
        rel = "index.html" if path in {"", "/"} else path.lstrip("/")
        candidate = (WEB_DIR / rel).resolve()
        root = WEB_DIR.resolve()
        if root not in candidate.parents and candidate != root:
            return self._send_text("Not found.", 404)
        if not candidate.is_file():
            return self._send_text("Not found.", 404)

        content_type, _ = mimetypes.guess_type(str(candidate))
        body = candidate.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type or "application/octet-stream")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        try:
            self._dispatch("GET")
        except AppError as exc:
            self._send_json({"error": exc.message}, exc.status)
        except Exception as exc:
            self._send_json({"error": str(exc)}, 500)

    def do_POST(self):
        try:
            self._dispatch("POST")
        except AppError as exc:
            self._send_json({"error": exc.message}, exc.status)
        except Exception as exc:
            self._send_json({"error": str(exc)}, 500)

    def log_message(self, format: str, *args):
        if os.getenv("MARKTRAIL_QUIET", "0") != "1":
            super().log_message(format, *args)


class MarkTrailServer(ThreadingHTTPServer):
    def __init__(self, address, db: Database, service: AppService):
        super().__init__(address, MarkTrailHandler)
        self.db = db
        self.service = service


def run(host: str | None = None, port: int | None = None):
    db = Database()
    seed_demo = os.getenv("MARKTRAIL_SEED_DEMO", "0") == "1"
    db.init(seed_demo=seed_demo)
    service = AppService(db)

    bind_host = host or os.getenv("MARKTRAIL_HOST", "127.0.0.1")
    bind_port = port or int(os.getenv("MARKTRAIL_PORT", "8000"))

    server = MarkTrailServer((bind_host, bind_port), db, service)
    print(f"MarkTrail running at http://{bind_host}:{bind_port}")
    if seed_demo:
        print(
            "Demo accounts enabled: admin/admin123 · lecturer/lecturer123 · "
            "reviewer/reviewer123 · exam_office/office123 · "
            "portal_operator/portal123 · student/student123"
        )
    print("Blockchain mode:", service.chain.config.mode)
    if service.chain.enabled:
        threading.Thread(
            target=service.recover_pending_batches,
            name="chain-startup-recovery",
            daemon=True,
        ).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
