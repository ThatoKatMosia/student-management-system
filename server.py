import json
import os
import re
import sqlite3
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse


ROOT = Path(__file__).resolve().parent
DATABASE = ROOT / "students.db"
FIELDS = ("student_id", "first_name", "last_name", "email", "course", "year", "status")
STATUSES = {"Active", "On leave", "Graduated"}
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
STUDENT_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")


@contextmanager
def connect_database():
    connection = sqlite3.connect(DATABASE)
    connection.row_factory = sqlite3.Row
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def initialize_database():
    DATABASE.parent.mkdir(parents=True, exist_ok=True)
    with connect_database() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS students (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id TEXT NOT NULL UNIQUE,
                first_name TEXT NOT NULL,
                last_name TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE,
                course TEXT NOT NULL,
                year INTEGER NOT NULL CHECK(year BETWEEN 1 AND 8),
                status TEXT NOT NULL CHECK(status IN ('Active', 'On leave', 'Graduated'))
            )
            """
        )


def validate_student(payload):
    if not isinstance(payload, dict):
        return None, "Request body must be a JSON object."

    student = {}
    for field in FIELDS:
        value = payload.get(field)
        if field == "year":
            if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 8:
                return None, "Year must be an integer between 1 and 8."
            student[field] = value
            continue
        if not isinstance(value, str) or not value.strip():
            return None, f"{field.replace('_', ' ').capitalize()} is required."
        student[field] = value.strip()

    if not STUDENT_ID_PATTERN.fullmatch(student["student_id"]):
        return None, "Student ID may contain only letters, numbers, hyphens, and underscores."
    if not EMAIL_PATTERN.fullmatch(student["email"]):
        return None, "Enter a valid email address."
    if student["status"] not in STATUSES:
        return None, "Status must be Active, On leave, or Graduated."
    return student, None


def student_dict(row):
    return dict(row)


class StudentHandler(BaseHTTPRequestHandler):
    def _send_json(self, status, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _send_static(self, filename):
        path = ROOT / filename
        if not path.is_file():
            self._send_json(404, {"error": "Not found."})
            return
        content_type = {
            ".html": "text/html; charset=utf-8",
            ".css": "text/css; charset=utf-8",
            ".js": "text/javascript; charset=utf-8",
        }[path.suffix]
        body = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self):
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > 1_000_000:
                raise ValueError
            return json.loads(self.rfile.read(length).decode("utf-8"))
        except (ValueError, UnicodeDecodeError, json.JSONDecodeError):
            return None

    def _student_id_from_path(self, path):
        match = re.fullmatch(r"/api/students/(\d+)", path)
        return int(match.group(1)) if match else None

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/":
            self._send_static("index.html")
            return
        if parsed.path in {"/index.html", "/styles.css", "/app.js"}:
            self._send_static(parsed.path.lstrip("/"))
            return
        if parsed.path == "/api/students":
            query = parse_qs(parsed.query).get("q", [""])[0].strip()
            with connect_database() as connection:
                if query:
                    pattern = f"%{query}%"
                    rows = connection.execute(
                        """
                        SELECT * FROM students
                        WHERE student_id LIKE ? OR first_name LIKE ? OR last_name LIKE ?
                            OR email LIKE ? OR course LIKE ? OR status LIKE ?
                        ORDER BY last_name COLLATE NOCASE, first_name COLLATE NOCASE
                        """,
                        (pattern, pattern, pattern, pattern, pattern, pattern),
                    ).fetchall()
                else:
                    rows = connection.execute(
                        "SELECT * FROM students ORDER BY last_name COLLATE NOCASE, first_name COLLATE NOCASE"
                    ).fetchall()
            self._send_json(200, {"students": [student_dict(row) for row in rows]})
            return
        student_id = self._student_id_from_path(parsed.path)
        if student_id is not None:
            with connect_database() as connection:
                row = connection.execute("SELECT * FROM students WHERE id = ?", (student_id,)).fetchone()
            if row is None:
                self._send_json(404, {"error": "Student not found."})
            else:
                self._send_json(200, {"student": student_dict(row)})
            return
        self._send_json(404, {"error": "Not found."})

    def do_POST(self):
        if urlparse(self.path).path != "/api/students":
            self._send_json(404, {"error": "Not found."})
            return
        payload = self._read_json()
        if payload is None:
            self._send_json(400, {"error": "A valid JSON request body is required."})
            return
        student, error = validate_student(payload)
        if error:
            self._send_json(400, {"error": error})
            return
        try:
            with connect_database() as connection:
                cursor = connection.execute(
                    """
                    INSERT INTO students (student_id, first_name, last_name, email, course, year, status)
                    VALUES (:student_id, :first_name, :last_name, :email, :course, :year, :status)
                    """,
                    student,
                )
                row = connection.execute(
                    "SELECT * FROM students WHERE id = ?", (cursor.lastrowid,)
                ).fetchone()
        except sqlite3.IntegrityError:
            self._send_json(409, {"error": "A student with this ID or email already exists."})
            return
        self._send_json(201, {"student": student_dict(row)})

    def do_PUT(self):
        parsed = urlparse(self.path)
        student_id = self._student_id_from_path(parsed.path)
        if student_id is None:
            self._send_json(404, {"error": "Not found."})
            return
        payload = self._read_json()
        if payload is None:
            self._send_json(400, {"error": "A valid JSON request body is required."})
            return
        student, error = validate_student(payload)
        if error:
            self._send_json(400, {"error": error})
            return
        try:
            with connect_database() as connection:
                cursor = connection.execute(
                    """
                    UPDATE students SET student_id = :student_id, first_name = :first_name,
                        last_name = :last_name, email = :email, course = :course,
                        year = :year, status = :status
                    WHERE id = :id
                    """,
                    {**student, "id": student_id},
                )
                if cursor.rowcount == 0:
                    self._send_json(404, {"error": "Student not found."})
                    return
                row = connection.execute("SELECT * FROM students WHERE id = ?", (student_id,)).fetchone()
        except sqlite3.IntegrityError:
            self._send_json(409, {"error": "A student with this ID or email already exists."})
            return
        self._send_json(200, {"student": student_dict(row)})

    def do_DELETE(self):
        parsed = urlparse(self.path)
        student_id = self._student_id_from_path(parsed.path)
        if student_id is None:
            self._send_json(404, {"error": "Not found."})
            return
        with connect_database() as connection:
            cursor = connection.execute("DELETE FROM students WHERE id = ?", (student_id,))
        if cursor.rowcount == 0:
            self._send_json(404, {"error": "Student not found."})
        else:
            self._send_json(200, {"message": "Student deleted."})

    def log_message(self, format_string, *args):
        super().log_message(format_string, *args)


def main():
    initialize_database()
    port = int(os.environ.get("PORT", "8080"))
    server = ThreadingHTTPServer(("127.0.0.1", port), StudentHandler)
    print(f"Student Management System running at http://127.0.0.1:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
