from __future__ import annotations

import json
import mimetypes
import os
import re
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
            body = self._body()
            session_id = login(
                self.db,
                str(body.get("username", "")),
                str(body.get("password", "")),
            )
            if not session_id:
                raise AppError("Invalid username or password.", 401)
            return self._send_json(
                {"ok": True},
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
                    }
                }
            )

        if method == "GET" and path == "/api/dashboard":
            return self._send_json(self.service.dashboard(user_id))

        if method == "GET" and path == "/api/status":
            return self._send_json({"chain": ChainClient().status()})

        if method == "GET" and path == "/api/student/marks":
            return self._send_json({"marks": self.service.student_marks(user_id)})

        if method == "GET" and path == "/api/student/reports":
            return self._send_json({"reports": self.service.student_reports(user_id)})

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

        match = re.fullmatch(r"/api/reviewer/batches/(0x[a-fA-F0-9]{64})/verify", path)
        if method == "POST" and match:
            return self._send_json(
                self.service.verify_batch(user_id, match.group(1))
            )

        match = re.fullmatch(r"/api/reviewer/batches/(0x[a-fA-F0-9]{64})/retry-chain", path)
        if method == "POST" and match:
            return self._send_json(self.service.retry_chain(user_id, match.group(1)))

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
                ),
                201,
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
                ),
                201,
            )

        match = re.fullmatch(r"/api/audit/batch/(0x[a-fA-F0-9]{64})", path)
        if method == "GET" and match:
            return self._send_json(
                self.service.batch_audit(user_id, match.group(1))
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
    db.init(seed_demo=os.getenv("MARKTRAIL_SEED_DEMO", "1") == "1")
    service = AppService(db)

    bind_host = host or os.getenv("MARKTRAIL_HOST", "127.0.0.1")
    bind_port = port or int(os.getenv("MARKTRAIL_PORT", "8000"))

    server = MarkTrailServer((bind_host, bind_port), db, service)
    print(f"MarkTrail running at http://{bind_host}:{bind_port}")
    print(
        "Demo accounts: admin/admin123 · lecturer/lecturer123 · "
        "reviewer/reviewer123 · student/student123"
    )
    print("Blockchain mode:", service.chain.config.mode)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
