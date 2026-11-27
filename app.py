"""Student marks and AI report-card portal.

Run locally with: flask --app app run --debug
"""

import csv
import hmac
import io
import json
import math
import os
import sqlite3
import zipfile
from datetime import datetime, timezone
from functools import wraps
from pathlib import Path

import requests
from dotenv import load_dotenv
from flask import Flask, g, jsonify, render_template, request

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = Path(os.getenv("DATABASE_PATH", BASE_DIR / "student_portal.db"))
GEMINI_API_KEY = (os.getenv("GEMINI_API") or os.getenv("GEMINI_API_KEY") or "").strip()
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")
EXTERNAL_API_KEY = os.getenv("APP_API_KEY")
WEBHOOK_URL = os.getenv("REPORT_WEBHOOK_URL")

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def db():
    if "db" not in g:
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


@app.teardown_appcontext
def close_db(_exception=None):
    db_conn = g.pop("db", None)
    if db_conn is not None:
        db_conn.close()


@app.after_request
def add_security_headers(response):
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    return response


def init_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS students (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                class_name TEXT NOT NULL DEFAULT '',
                attendance REAL NOT NULL DEFAULT 0,
                notes TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS marks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id TEXT NOT NULL REFERENCES students(id) ON DELETE CASCADE,
                subject TEXT NOT NULL,
                score REAL NOT NULL,
                max_score REAL NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(student_id, subject)
            );
            CREATE TABLE IF NOT EXISTS reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id TEXT NOT NULL REFERENCES students(id) ON DELETE CASCADE,
                payload TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
        """)
        conn.commit()
    finally:
        conn.close()


def student_record(conn, student_id):
    row = conn.execute("SELECT * FROM students WHERE id = ?", (student_id,)).fetchone()
    if row is None:
        return None
    student = dict(row)
    student["marks"] = [dict(mark) for mark in conn.execute(
        "SELECT subject, score, max_score FROM marks WHERE student_id = ? ORDER BY subject",
        (student_id,),
    )]
    total_score = sum(m["score"] for m in student["marks"])
    total_max = sum(m["max_score"] for m in student["marks"])
    student["average"] = round(100 * total_score / total_max, 1) if total_max > 0 else 0
    student["has_report"] = bool(conn.execute(
        "SELECT 1 FROM reports WHERE student_id = ? LIMIT 1", (student_id,)
    ).fetchone())
    return student


def clean_student_input(data):
    if not isinstance(data, dict):
        raise ValueError("Student data must be a JSON object.")
    student_id = str(data.get("id") or "").strip()
    name = str(data.get("name") or "").strip()
    if not student_id or len(student_id) > 40:
        raise ValueError("Student ID is required and must be 40 characters or fewer.")
    if not name or len(name) > 120:
        raise ValueError("Student name is required and must be 120 characters or fewer.")
    class_name = str(data.get("class_name") or "").strip()[:80]
    notes = str(data.get("notes") or "").strip()[:1000]

    raw_att = data.get("attendance")
    if raw_att is None or raw_att == "":
        attendance = 0.0
    else:
        try:
            attendance = float(raw_att)
        except (ValueError, TypeError):
            raise ValueError("Attendance must be a valid number between 0 and 100.")
    if math.isnan(attendance) or math.isinf(attendance) or not (0 <= attendance <= 100):
        raise ValueError("Attendance must be between 0 and 100.")

    marks = data.get("marks")
    if marks is None:
        marks = []
    if not isinstance(marks, list) or len(marks) > 100:
        raise ValueError("Marks must be a list with no more than 100 subjects.")
    cleaned_marks = []
    seen = set()
    for mark in marks:
        if not isinstance(mark, dict):
            raise ValueError("Each subject entry must be an object.")
        subject = str(mark.get("subject") or "").strip()[:100]
        if not subject or subject.casefold() in seen:
            raise ValueError("Each subject must have a unique, non-empty name.")
        try:
            score = float(mark.get("score") if mark.get("score") is not None else 0)
            max_score = float(mark.get("max_score") if mark.get("max_score") is not None else 100)
        except (ValueError, TypeError):
            raise ValueError(f"Scores for {subject} must be valid numbers.")
        if math.isnan(score) or math.isinf(score) or math.isnan(max_score) or math.isinf(max_score):
            raise ValueError(f"Scores for {subject} must be finite numbers.")
        if max_score <= 0 or score < 0 or score > max_score:
            raise ValueError(f"Marks for {subject} must be between 0 and the maximum score.")
        seen.add(subject.casefold())
        cleaned_marks.append({"subject": subject, "score": score, "max_score": max_score})
    return {
        "id": student_id, "name": name, "class_name": class_name,
        "attendance": attendance, "notes": notes, "marks": cleaned_marks,
    }


def save_student(data, replace_marks=True):
    student = clean_student_input(data)
    conn = db()
    conn.execute("""INSERT INTO students(id,name,class_name,attendance,notes,updated_at)
        VALUES(?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET name=excluded.name,
        class_name=excluded.class_name, attendance=excluded.attendance,
        notes=excluded.notes, updated_at=excluded.updated_at""",
        (student["id"], student["name"], student["class_name"],
         student["attendance"], student["notes"], now_iso()))
    if replace_marks:
        conn.execute("DELETE FROM marks WHERE student_id = ?", (student["id"],))
        conn.executemany("""INSERT INTO marks(student_id,subject,score,max_score,updated_at)
            VALUES(?,?,?,?,?)""", [
            (student["id"], mark["subject"], mark["score"], mark["max_score"], now_iso())
            for mark in student["marks"]
        ])
    conn.commit()
    return student_record(conn, student["id"])


def parse_num(val, default=0.0):
    if val is None or val == "":
        return default
    if isinstance(val, (int, float)):
        num = float(val)
        return default if math.isnan(num) or math.isinf(num) else num
    val_str = str(val).strip().rstrip("%").strip()
    try:
        num = float(val_str)
        return default if math.isnan(num) or math.isinf(num) else num
    except (ValueError, TypeError):
        return default


def parse_import(file_storage):
    filename = (file_storage.filename or "").lower()
    raw = file_storage.read()
    if len(raw) > 5 * 1024 * 1024:
        raise ValueError("File is larger than the 5 MB upload limit.")
    if filename.endswith(".csv"):
        try:
            text = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            text = raw.decode("latin-1")
        reader = csv.DictReader(io.StringIO(text))
        rows = list(reader)
    elif filename.endswith(".xlsx"):
        try:
            from openpyxl import load_workbook
        except ImportError as exc:
            raise RuntimeError("Excel import needs openpyxl. Install project requirements first.") from exc
        try:
            workbook = load_workbook(io.BytesIO(raw), read_only=True, data_only=True)
            try:
                sheet = workbook.active
                if sheet is None:
                    raise ValueError("Excel file has no active sheet.")
                values = sheet.iter_rows(values_only=True)
                headings = [str(v or "").strip().lower() for v in next(values, ())]
                rows = [dict(zip(headings, row)) for row in values]
            finally:
                workbook.close()
        except ValueError:
            raise
        except Exception as exc:
            raise ValueError(f"Invalid or corrupted Excel file: {exc}") from exc
    else:
        raise ValueError("Upload a .csv or .xlsx file.")

    normalized = [{str(k or "").strip().lower(): v for k, v in row.items()} for row in rows]
    aliases = {
        "id": ("id", "student_id", "student id", "roll_no", "roll no"),
        "name": ("name", "student_name", "student name"),
        "class_name": ("class", "class_name", "class name", "grade"),
        "attendance": ("attendance", "attendance_percent", "attendance %"),
        "subject": ("subject", "course"),
        "score": ("score", "marks", "obtained", "marks_obtained"),
        "max_score": ("max_score", "max marks", "out_of", "total_marks"),
        "notes": ("notes", "details", "student_details"),
    }

    def value(row, key, default=""):
        for alias in aliases[key]:
            if alias in row and row[alias] is not None:
                return row[alias]
        return default

    students = {}
    for row in normalized:
        student_id = str(value(row, "id") or "").strip()
        name = str(value(row, "name") or "").strip()
        if not student_id or not name:
            continue
        if student_id not in students:
            students[student_id] = {
                "id": student_id, "name": name,
                "class_name": str(value(row, "class_name") or "").strip(),
                "attendance": parse_num(value(row, "attendance", 0), 0.0),
                "notes": str(value(row, "notes") or "").strip(),
                "marks": [],
            }
        else:
            if not students[student_id]["class_name"] and value(row, "class_name"):
                students[student_id]["class_name"] = str(value(row, "class_name")).strip()
            if not students[student_id]["notes"] and value(row, "notes"):
                students[student_id]["notes"] = str(value(row, "notes")).strip()
            if students[student_id]["attendance"] == 0 and value(row, "attendance"):
                students[student_id]["attendance"] = parse_num(value(row, "attendance"), 0.0)

        subject = str(value(row, "subject") or "").strip()
        if subject:
            score = parse_num(value(row, "score", 0), 0.0)
            max_score = parse_num(value(row, "max_score", 100), 100.0)
            students[student_id]["marks"].append({
                "subject": subject,
                "score": score,
                "max_score": max_score,
            })
    if not students:
        raise ValueError("No valid rows found. Include student_id and name columns.")
    return list(students.values())


def generate_report(student):
    api_key = (os.getenv("GEMINI_API") or os.getenv("GEMINI_API_KEY") or GEMINI_API_KEY or "").strip()
    if not api_key:
        raise RuntimeError("Add GEMINI_API to .env before generating AI remarks.")
    model_name = (os.getenv("GEMINI_MODEL") or GEMINI_MODEL or "gemini-3.5-flash-lite").strip()

    total = sum(mark["score"] for mark in student["marks"])
    maximum = sum(mark["max_score"] for mark in student["marks"])
    average = round((total / maximum) * 100, 1) if maximum else 0
    grade = "A" if average >= 90 else "B" if average >= 80 else "C" if average >= 70 else "D" if average >= 60 else "Needs support"

    prompt_data = {
        "class": student["class_name"], "attendance_percent": student["attendance"],
        "overall_average_percent": average,
        "subject_results": [
            {"subject": m["subject"], "score": m["score"], "maximum": m["max_score"],
             "percent": round(100 * m["score"] / m["max_score"], 1)}
            for m in student["marks"]
        ],
        "educator_context": student["notes"],
    }
    body = {
        "systemInstruction": {"parts": [{"text": (
            "Write a supportive, concise student report card remark (70-110 words) based only on the supplied academic data in <academic_data>. "
            "Mention one demonstrated strength, one specific area for improvement if supported by the data, and an actionable next step. "
            "Do not infer personality, health, family circumstances, or causes of performance. Do not invent facts. "
            "Refer to the student naturally (e.g. 'the student' or 'they/their'); do not insert bracketed placeholders like '[Student Name]'. "
            "Return only the remark text."
        )}]},
        "contents": [{"role": "user", "parts": [{"text": f"<academic_data>{json.dumps(prompt_data, ensure_ascii=False)}</academic_data>"}]}],
        "generationConfig": {"temperature": 0.3, "maxOutputTokens": 500},
    }
    response = requests.post(
        f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent",
        headers={"Content-Type": "application/json", "x-goog-api-key": api_key},
        json=body, timeout=45,
    )
    if response.status_code == 429:
        raise RuntimeError("Gemini rate limit reached. Please try again shortly.")
    if not response.ok:
        try:
            err_data = response.json()
            err_msg = err_data.get("error", {}).get("message", response.text)
        except Exception:
            err_msg = response.text
        app.logger.warning("Gemini error (%d): %s", response.status_code, err_msg)
        if response.status_code in (400, 403, 404):
            raise RuntimeError(f"Gemini API error ({response.status_code}): {err_msg}")
        response.raise_for_status()

    data = response.json()
    candidates = data.get("candidates", [])
    parts = (candidates[0].get("content") or {}).get("parts") or [] if candidates else []
    remark = "\n".join(
        p.get("text", "") for p in parts
        if isinstance(p, dict) and p.get("text") and not p.get("thought")
    ).strip()
    if not remark:
        raise RuntimeError("Gemini returned an empty remark.")

    # Substitute any residual bracketed student placeholders cleanly
    remark = (
        remark.replace("[Student Name]", student["name"])
        .replace("[Student's Name]", f"{student['name']}'s")
        .replace("[Student]", student["name"])
    )

    report = {
        "student_id": student["id"], "student_name": student["name"],
        "class_name": student["class_name"], "attendance": student["attendance"],
        "marks": student["marks"], "average": average, "grade": grade,
        "remark": remark, "created_at": now_iso(),
    }
    conn = db()
    conn.execute("INSERT INTO reports(student_id,payload,created_at) VALUES(?,?,?)",
                 (student["id"], json.dumps(report, ensure_ascii=False), report["created_at"]))
    conn.commit()
    send_webhook(report)
    return report


def send_webhook(report):
    if not WEBHOOK_URL:
        return
    url = WEBHOOK_URL.strip()
    if not (url.startswith("http://") or url.startswith("https://")):
        app.logger.warning("Invalid webhook URL scheme: %s", url)
        return
    try:
        requests.post(url, json={"event": "report.generated", "data": report}, timeout=5)
    except requests.RequestException as exc:
        app.logger.warning("Report webhook delivery failed: %s", exc)


def require_api_key(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        expected = (os.getenv("APP_API_KEY") or EXTERNAL_API_KEY or "").strip()
        supplied = request.headers.get("X-API-Key", "").strip() or request.headers.get("Authorization", "").replace("Bearer ", "").strip()
        if not expected or not supplied or not hmac.compare_digest(supplied, expected):
            return jsonify(error="Unauthorized", message="Supply a valid X-API-Key."), 401
        return fn(*args, **kwargs)
    return wrapped


@app.get("/")
def home():
    return render_template("index.html")


@app.get("/api/students")
def list_students():
    conn = db()
    ids = [row["id"] for row in conn.execute("SELECT id FROM students ORDER BY name")]
    students = [student_record(conn, student_id) for student_id in ids]
    report_count = conn.execute("SELECT COUNT(*) FROM reports").fetchone()[0]
    return jsonify(students=students, report_count=report_count)


@app.post("/api/students")
def create_or_update_student():
    data = request.get_json(silent=True)
    if data is None and request.data:
        return jsonify(error="Invalid JSON body."), 400
    try:
        student = save_student(data or {})
        return jsonify(student=student), 201
    except (ValueError, TypeError, KeyError) as exc:
        return jsonify(error=str(exc)), 400


@app.delete("/api/students/<path:student_id>")
def delete_student(student_id):
    conn = db()
    cur = conn.execute("DELETE FROM students WHERE id = ?", (student_id,))
    conn.commit()
    if not cur.rowcount:
        return jsonify(error="Student not found."), 404
    return jsonify(ok=True)


@app.post("/api/import")
def import_marks():
    if "file" not in request.files:
        return jsonify(error="Choose a CSV or Excel file."), 400
    try:
        records = parse_import(request.files["file"])
        cleaned = [clean_student_input(r) for r in records]
        conn = db()
        with conn:
            for student in cleaned:
                conn.execute("""INSERT INTO students(id,name,class_name,attendance,notes,updated_at)
                    VALUES(?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET name=excluded.name,
                    class_name=excluded.class_name, attendance=excluded.attendance,
                    notes=excluded.notes, updated_at=excluded.updated_at""",
                    (student["id"], student["name"], student["class_name"],
                     student["attendance"], student["notes"], now_iso()))
                conn.execute("DELETE FROM marks WHERE student_id = ?", (student["id"],))
                conn.executemany("""INSERT INTO marks(student_id,subject,score,max_score,updated_at)
                    VALUES(?,?,?,?,?)""", [
                    (student["id"], mark["subject"], mark["score"], mark["max_score"], now_iso())
                    for mark in student["marks"]
                ])
        saved = [student_record(conn, student["id"]) for student in cleaned]
        return jsonify(imported=len(saved), students=saved), 201
    except (ValueError, RuntimeError, UnicodeDecodeError, csv.Error) as exc:
        return jsonify(error=str(exc)), 400


@app.post("/api/students/<path:student_id>/report")
def create_report(student_id):
    conn = db()
    student = student_record(conn, student_id)
    if not student:
        return jsonify(error="Student not found."), 404
    if not student["marks"]:
        return jsonify(error="Add at least one subject mark before generating a report."), 400
    try:
        return jsonify(report=generate_report(student)), 201
    except requests.exceptions.Timeout:
        return jsonify(error="Gemini request timed out. Try again."), 504
    except requests.exceptions.RequestException as exc:
        app.logger.warning("Gemini request failed: %s", exc)
        return jsonify(error="Could not reach Gemini. Check the API key and connection."), 502
    except RuntimeError as exc:
        return jsonify(error=str(exc)), 503


@app.get("/api/students/<path:student_id>/report")
def latest_report(student_id):
    conn = db()
    row = conn.execute("SELECT payload FROM reports WHERE student_id=? ORDER BY id DESC LIMIT 1",
                       (student_id,)).fetchone()
    if not row:
        return jsonify(error="No report card has been generated yet."), 404
    return jsonify(report=json.loads(row["payload"]))


@app.get("/api/docs")
def api_docs():
    return jsonify({
        "name": "Student Report Generator API",
        "authentication": "External endpoints require X-API-Key set by APP_API_KEY in .env.",
        "endpoints": [
            {"method": "GET", "path": "/api/v1/students", "description": "List students and marks."},
            {"method": "POST", "path": "/api/v1/students", "description": "Create or update a student and marks. JSON body matches the student object returned by GET."},
            {"method": "GET", "path": "/api/v1/students/<student_id>/report", "description": "Get latest generated report card."},
            {"method": "POST", "path": "/api/v1/students/<student_id>/report", "description": "Generate a report card and AI remark."},
        ],
        "import_columns": "student_id,name,class,attendance,notes,subject,score,max_score (one row per student and subject)",
        "webhook": "Set REPORT_WEBHOOK_URL to receive report.generated JSON events.",
    })


@app.get("/api/v1/students")
@require_api_key
def external_students():
    return list_students()


@app.post("/api/v1/students")
@require_api_key
def external_upsert_student():
    return create_or_update_student()


@app.get("/api/v1/students/<path:student_id>/report")
@require_api_key
def external_latest_report(student_id):
    return latest_report(student_id)


@app.post("/api/v1/students/<path:student_id>/report")
@require_api_key
def external_create_report(student_id):
    return create_report(student_id)


@app.errorhandler(413)
def too_large(_error):
    return jsonify(error="Upload exceeds the 5 MB limit."), 413


init_db()

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=int(os.getenv("PORT", "5000")), debug=os.getenv("FLASK_DEBUG") == "1")
