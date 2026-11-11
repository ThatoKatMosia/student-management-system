import json
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from pathlib import Path

import server


class StudentApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_directory = tempfile.TemporaryDirectory()
        cls.original_database = server.DATABASE
        server.DATABASE = Path(cls.temp_directory.name) / "test-students.db"
        server.initialize_database()
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.StudentHandler)
        cls.base_url = f"http://{cls.httpd.server_address[0]}:{cls.httpd.server_port}"
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        cls.thread.join()
        server.DATABASE = cls.original_database
        cls.temp_directory.cleanup()

    def setUp(self):
        with server.connect_database() as connection:
            connection.execute("DELETE FROM students")

    def request_json(self, path, method="GET", body=None, expected_status=200):
        data = None if body is None else json.dumps(body).encode("utf-8")
        request = Request(
            f"{self.base_url}{path}",
            data=data,
            method=method,
            headers={"Content-Type": "application/json"},
        )
        try:
            response = urlopen(request)
        except HTTPError as error:
            response = error
        with response:
            payload = json.loads(response.read().decode("utf-8"))
            self.assertEqual(response.status, expected_status, payload)
            return payload

    def create_student(self, student_id="STU-1001", email="alex@example.edu"):
        return self.request_json(
            "/api/students",
            method="POST",
            expected_status=201,
            body={
                "student_id": student_id,
                "first_name": "Alex",
                "last_name": "Morgan",
                "email": email,
                "course": "Computer Science",
                "year": 2,
                "status": "Active",
            },
        )["student"]

    def test_create_list_search_update_and_delete(self):
        student = self.create_student()
        student_id = student["id"]
        details = self.request_json(f"/api/students/{student_id}")
        self.assertEqual(details["student"]["email"], "alex@example.edu")

        listing = self.request_json("/api/students")
        self.assertEqual([item["id"] for item in listing["students"]], [student_id])
        search = self.request_json("/api/students?q=Computer")
        self.assertEqual(len(search["students"]), 1)

        updated = {
            "student_id": "STU-1001",
            "first_name": "Alex",
            "last_name": "Morgan",
            "email": "alex@example.edu",
            "course": "Data Science",
            "year": 3,
            "status": "On leave",
        }
        result = self.request_json(
            f"/api/students/{student_id}", method="PUT", body=updated
        )
        self.assertEqual(result["student"]["course"], "Data Science")
        self.assertEqual(result["student"]["year"], 3)
        self.assertEqual(result["student"]["status"], "On leave")

        deleted = self.request_json(f"/api/students/{student_id}", method="DELETE")
        self.assertEqual(deleted["message"], "Student deleted.")
        self.assertEqual(self.request_json("/api/students")["students"], [])
        self.request_json(f"/api/students/{student_id}", expected_status=404)

    def test_rejects_invalid_student_and_duplicate_identifiers(self):
        invalid = {
            "student_id": "STU-1002",
            "first_name": "Sam",
            "last_name": "Lee",
            "email": "not-an-email",
            "course": "Biology",
            "year": 2.5,
            "status": "Active",
        }
        self.request_json("/api/students", method="POST", body=invalid, expected_status=400)

        self.create_student()
        self.request_json(
            "/api/students",
            method="POST",
            expected_status=409,
            body={
                "student_id": "STU-1001",
                "first_name": "Taylor",
                "last_name": "Reed",
                "email": "taylor@example.edu",
                "course": "Mathematics",
                "year": 1,
                "status": "Active",
            },
        )

    def test_rejects_non_integer_years_and_student_ids_with_spaces(self):
        base_student = {
            "student_id": "STU-1003",
            "first_name": "Sam",
            "last_name": "Lee",
            "email": "sam@example.edu",
            "course": "Biology",
            "year": 2,
            "status": "Active",
        }
        for year in (2.5, True, False, "2.5"):
            with self.subTest(year=year):
                self.request_json(
                    "/api/students",
                    method="POST",
                    body={**base_student, "year": year},
                    expected_status=400,
                )

        self.request_json(
            "/api/students",
            method="POST",
            body={**base_student, "student_id": "STU 1003"},
            expected_status=400,
        )
        self.assertEqual(self.request_json("/api/students")["students"], [])

    def test_unknown_api_route_returns_not_found(self):
        self.request_json("/api/unknown", expected_status=404)


if __name__ == "__main__":
    unittest.main()
