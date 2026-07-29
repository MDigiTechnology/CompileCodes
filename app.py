"""Multi-language Online Compiler — Flask backend."""

import os
import re
import sqlite3
import subprocess
import tempfile
import threading
import time
import uuid
from pathlib import Path

from flask import Flask, jsonify, render_template, request

app = Flask(__name__)

MAX_CODE_LENGTH = 50_000
EXECUTION_TIMEOUT = 10
COMPILE_TIMEOUT = 15
SUPPORTED_LANGUAGES = {"python", "java", "cpp", "sql"}

# In-memory SQL sessions — cleared on page refresh (new session_id per load).
SQL_SESSIONS: dict[str, dict] = {}
SQL_SESSION_LOCK = threading.Lock()
SQL_SESSION_TTL = 3600  # seconds

_APP_DIR = Path(__file__).resolve().parent
_VENV_PYTHON = _APP_DIR / "myenv" / "bin" / "python3"
PYTHON_EXECUTABLE = os.environ.get(
    "PYTHON_EXECUTABLE",
    str(_VENV_PYTHON) if _VENV_PYTHON.is_file() else "python3",
)
GXX_EXECUTABLE = os.environ.get("GXX_EXECUTABLE", "g++")

def _find_bundled_jdk() -> tuple[str, str] | None:
    tools_dir = _APP_DIR / "tools"
    if not tools_dir.is_dir():
        return None
    for jdk_dir in sorted(tools_dir.glob("jdk-*"), reverse=True):
        javac = jdk_dir / "bin" / "javac"
        java = jdk_dir / "bin" / "java"
        if javac.is_file() and java.is_file():
            return str(javac), str(java)
    return None

_bundled_jdk = _find_bundled_jdk()
JAVAC_EXECUTABLE = os.environ.get(
    "JAVAC_EXECUTABLE",
    _bundled_jdk[0] if _bundled_jdk else "javac",
)
JAVA_EXECUTABLE = os.environ.get(
    "JAVA_EXECUTABLE",
    _bundled_jdk[1] if _bundled_jdk else "java",
)

TEMP_DIR = Path(tempfile.gettempdir()) / "codecompiler"
TEMP_DIR.mkdir(exist_ok=True)

MINIMAL_ENV = {
    "PATH": os.environ.get("PATH", ""),
    "HOME": os.environ.get("HOME", "/tmp"),
    "LANG": "C.UTF-8",
    "MPLCONFIGDIR": str(TEMP_DIR / "mplconfig"),
}

SITE = {
    "name": os.environ.get("SITE_NAME", "CompileCode"),
    "url": os.environ.get("SITE_URL", "https://compilecodes.com").rstrip("/"),
    "tagline": "Free Online Python, Java, C++ & SQL Compiler",
    "description": (
        "Run Python, Java, C++, and SQL online for free. "
        "Instant compile and execute with numpy, pandas, matplotlib, and ML libraries. "
        "No signup required."
    ),
    "keywords": (
        "online compiler, compile code online, python compiler online, java compiler, c++ compiler, "
        "sql online, run python online, online ide, code runner, free compiler"
    ),
    "author": os.environ.get("SITE_AUTHOR", "Manish"),
    "privacy_updated": "July 29, 2026",
    "google_site_verification": os.environ.get("GOOGLE_SITE_VERIFICATION", ""),
    "ga_id": os.environ.get("GA_MEASUREMENT_ID", ""),
    "adsense_client": os.environ.get("ADSENSE_CLIENT_ID", ""),
    "adsense_slot_top": os.environ.get("ADSENSE_SLOT_TOP", ""),
    "adsense_slot_bottom": os.environ.get("ADSENSE_SLOT_BOTTOM", ""),
}

COMPILER_LANDINGS = {
    "python": {
        "path": "/online-python-compiler",
        "default_lang": "python",
        "seo_title": "Online Python Compiler — Run Python Code Free | CompileCode",
        "seo_description": (
            "Run Python online instantly. Free browser IDE with compile and execute, "
            "ideal for scripts, learning, and data science with numpy and pandas on the server."
        ),
        "seo_keywords": (
            "online python compiler, run python online, python ide, execute python code, "
            "python online editor, free python compiler"
        ),
        "seo_h1": "Free Online Python Compiler",
        "seo_intro": {
            "heading": "Run Python in your browser",
            "paragraphs": [
                "Write Python code and click Run to see output immediately. No installation or account needed.",
                "Use this page to practice syntax, test algorithms, or run short data scripts when your machine is not set up for Python.",
            ],
        },
        "faq_items": [
            {
                "question": "Can I run Python online for free?",
                "answer": "Yes. This online Python compiler is free and runs your code on our server with a short time limit per execution.",
            },
            {
                "question": "Which Python libraries are available?",
                "answer": "Common libraries such as numpy, pandas, and matplotlib may be available if installed on the server hosting this site.",
            },
        ],
    },
    "java": {
        "path": "/online-java-compiler",
        "default_lang": "java",
        "seo_title": "Online Java Compiler — Compile & Run Java Free | CompileCode",
        "seo_description": (
            "Compile and run Java online. Free JDK-based compiler for public classes with main method — "
            "perfect for homework, interviews, and quick tests."
        ),
        "seo_keywords": (
            "online java compiler, compile java online, run java online, java ide, "
            "java online editor, free java compiler"
        ),
        "seo_h1": "Free Online Java Compiler",
        "seo_intro": {
            "heading": "Compile and run Java online",
            "paragraphs": [
                "Paste a public class with a main method and run it in seconds. Errors from javac and the JVM are shown in the output panel.",
                "Use standard Java syntax — class name must match the public class in your file.",
            ],
        },
        "faq_items": [
            {
                "question": "Do I need to install JDK locally?",
                "answer": "No. The server compiles with javac and runs with java for you in the browser.",
            },
        ],
    },
    "cpp": {
        "path": "/online-cpp-compiler",
        "default_lang": "cpp",
        "seo_title": "Online C++ Compiler — Run C++ Code Free | CompileCode",
        "seo_description": (
            "Online C++ compiler using g++ (C++17). Write, compile, and execute C++ programs in your browser for free."
        ),
        "seo_keywords": (
            "online c++ compiler, compile c++ online, run c++ online, cpp ide, "
            "c++ online editor, g++ online"
        ),
        "seo_h1": "Free Online C++ Compiler",
        "seo_intro": {
            "heading": "Build and run C++ online",
            "paragraphs": [
                "Use #include, cout, and standard C++17 features. Compilation errors and runtime output appear in the console.",
                "Great for competitive programming practice and university assignments.",
            ],
        },
        "faq_items": [
            {
                "question": "Which C++ standard is used?",
                "answer": "Programs are compiled with g++ using the C++17 standard.",
            },
        ],
    },
    "sql": {
        "path": "/online-sql-compiler",
        "default_lang": "sql",
        "seo_title": "Online SQL Compiler — Practice SQL Free | CompileCode",
        "seo_description": (
            "Run SQL online against a temporary in-memory database. CREATE TABLE, INSERT, SELECT, and more — "
            "resets when you refresh."
        ),
        "seo_keywords": (
            "online sql compiler, run sql online, sql practice, sqlite online, "
            "sql editor free, test sql queries"
        ),
        "seo_h1": "Free Online SQL Compiler",
        "seo_intro": {
            "heading": "Practice SQL with an in-memory database",
            "paragraphs": [
                "Execute multiple statements separated by semicolons. Result sets render as tables in the output area.",
                "Data is not persisted — refresh the page to start with a clean database.",
            ],
        },
        "faq_items": [
            {
                "question": "Is my SQL data saved?",
                "answer": "No. SQL runs in an in-memory SQLite session that clears when you reload the page.",
            },
        ],
    },
}


def _compiler_template(page: str, **extra):
    landing = COMPILER_LANDINGS.get(page)
    ctx = {"page": page, "canonical_path": "/"}
    if landing:
        ctx.update(
            {
                "canonical_path": landing["path"],
                "default_lang": landing["default_lang"],
                "seo_title": landing["seo_title"],
                "seo_description": landing["seo_description"],
                "seo_keywords": landing["seo_keywords"],
                "seo_h1": landing["seo_h1"],
                "seo_intro": landing.get("seo_intro"),
                "faq_items": landing.get("faq_items"),
            }
        )
    ctx.update(extra)
    return render_template("index.html", **ctx)


@app.context_processor
def inject_site():
    return {"site": SITE}


@app.route("/")
def index():
    return _compiler_template(
        "home",
        canonical_path="/",
        seo_intro={
            "heading": "Free online compiler for Python, Java, C++, and SQL",
            "paragraphs": [
                "CompileCode is a browser-based IDE to write and run code without installing anything.",
                "Choose a language tab, press Run, and see output instantly — built for learners, interviews, and quick experiments.",
            ],
        },
    )


@app.route("/online-python-compiler")
def python_compiler():
    return _compiler_template("python")


@app.route("/online-java-compiler")
def java_compiler():
    return _compiler_template("java")


@app.route("/online-cpp-compiler")
def cpp_compiler():
    return _compiler_template("cpp")


@app.route("/online-sql-compiler")
def sql_compiler():
    return _compiler_template("sql")


@app.route("/about")
def about():
    return render_template("about.html", page="about")


@app.route("/privacy")
def privacy():
    return render_template("privacy.html", page="privacy")


@app.route("/terms")
def terms():
    return render_template("terms.html", page="terms")


@app.route("/robots.txt")
def robots_txt():
    content = f"""User-agent: *
Allow: /

Sitemap: {SITE['url']}/sitemap.xml
"""
    return content, 200, {"Content-Type": "text/plain; charset=utf-8"}


@app.route("/sitemap.xml")
def sitemap_xml():
    pages = [
        ("", "daily", "1.0"),
        ("/online-python-compiler", "weekly", "0.9"),
        ("/online-java-compiler", "weekly", "0.9"),
        ("/online-cpp-compiler", "weekly", "0.9"),
        ("/online-sql-compiler", "weekly", "0.9"),
        ("/about", "monthly", "0.8"),
        ("/privacy", "yearly", "0.3"),
        ("/terms", "yearly", "0.3"),
    ]
    urls = "\n".join(
        f"""  <url>
    <loc>{SITE['url']}{path}</loc>
    <changefreq>{freq}</changefreq>
    <priority>{priority}</priority>
  </url>"""
        for path, freq, priority in pages
    )
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
{urls}
</urlset>"""
    return xml, 200, {"Content-Type": "application/xml; charset=utf-8"}


@app.route("/ads.txt")
def ads_txt():
    client = SITE["adsense_client"]
    if not client:
        return "No ads configured.", 404, {"Content-Type": "text/plain; charset=utf-8"}
    pub_id = client.replace("ca-", "pub-") if client.startswith("ca-") else client
    content = f"google.com, {pub_id}, DIRECT, f08c47fec0942fa0\n"
    return content, 200, {"Content-Type": "text/plain; charset=utf-8"}


@app.route("/site.webmanifest")
def webmanifest():
    manifest = {
        "name": SITE["name"],
        "short_name": SITE["name"],
        "description": SITE["description"],
        "start_url": "/",
        "display": "standalone",
        "background_color": "#0d1117",
        "theme_color": "#3776ab",
        "icons": [{"src": "/static/img/icon-192.png", "sizes": "192x192", "type": "image/png"}],
    }
    return jsonify(manifest)




@app.route("/api/run", methods=["POST"])
def run_code():
    data = request.get_json(silent=True)
    if not data or "code" not in data:
        return jsonify({"success": False, "error": "No code provided."}), 400

    code = data["code"]
    language = data.get("language", "python").lower()

    if language not in SUPPORTED_LANGUAGES:
        return jsonify({
            "success": False,
            "error": f"Unsupported language: {language}. Choose python, java, cpp, or sql.",
        }), 400

    if not isinstance(code, str):
        return jsonify({"success": False, "error": "Invalid code format."}), 400

    if len(code) > MAX_CODE_LENGTH:
        return jsonify({
            "success": False,
            "error": f"Code exceeds maximum length of {MAX_CODE_LENGTH:,} characters.",
        }), 400

    if not code.strip():
        return jsonify({"success": False, "error": "Code cannot be empty."}), 400

    runners = {
        "python": lambda c: execute_python(c),
        "java": lambda c: execute_java(c),
        "cpp": lambda c: execute_cpp(c),
        "sql": lambda c: execute_sql(c, data.get("session_id")),
    }
    return jsonify(runners[language](code))


def _success(output: str) -> dict:
    return {
        "success": True,
        "output": output or "(Program finished with no output)",
        "error": None,
    }


def _failure(error: str, output: str | None = None) -> dict:
    return {"success": False, "output": output, "error": error}


def _run_command(cmd: list[str], cwd: Path, timeout: int) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
        cwd=str(cwd),
        env={**MINIMAL_ENV, "PYTHONDONTWRITEBYTECODE": "1", "PYTHONUNBUFFERED": "1"},
    )


def execute_python(code: str) -> dict:
    run_id = uuid.uuid4().hex
    work_dir = TEMP_DIR / run_id
    work_dir.mkdir(exist_ok=True)
    source = work_dir / "main.py"

    try:
        source.write_text(code, encoding="utf-8")
        proc = _run_command([PYTHON_EXECUTABLE, str(source)], work_dir, EXECUTION_TIMEOUT)

        if proc.returncode == 0:
            return _success(proc.stdout)

        return _failure(proc.stderr or f"Process exited with code {proc.returncode}", proc.stdout)

    except subprocess.TimeoutExpired:
        return _failure(f"Execution timed out after {EXECUTION_TIMEOUT} seconds.")
    except FileNotFoundError:
        return _failure(f"Python interpreter not found: {PYTHON_EXECUTABLE}")
    except Exception as exc:
        return _failure(f"Internal error: {exc}")
    finally:
        _cleanup_dir(work_dir)


def execute_cpp(code: str) -> dict:
    run_id = uuid.uuid4().hex
    work_dir = TEMP_DIR / run_id
    work_dir.mkdir(exist_ok=True)
    source = work_dir / "main.cpp"
    binary = work_dir / "main"

    try:
        source.write_text(code, encoding="utf-8")

        compile_proc = _run_command(
            [GXX_EXECUTABLE, "-Wall", "-std=c++17", "-o", str(binary), str(source)],
            work_dir,
            COMPILE_TIMEOUT,
        )
        if compile_proc.returncode != 0:
            return _failure(compile_proc.stderr or "Compilation failed.", compile_proc.stdout)

        run_proc = _run_command([str(binary)], work_dir, EXECUTION_TIMEOUT)
        if run_proc.returncode == 0:
            return _success(run_proc.stdout)

        return _failure(run_proc.stderr or f"Process exited with code {run_proc.returncode}", run_proc.stdout)

    except subprocess.TimeoutExpired:
        return _failure(f"Execution timed out after {EXECUTION_TIMEOUT} seconds.")
    except FileNotFoundError:
        return _failure(f"C++ compiler not found: {GXX_EXECUTABLE}. Install with: sudo apt install build-essential")
    except Exception as exc:
        return _failure(f"Internal error: {exc}")
    finally:
        _cleanup_dir(work_dir)


def execute_java(code: str) -> dict:
    class_name = extract_java_class_name(code)
    if not class_name:
        return _failure(
            "Could not find a public class. Java code must contain: public class ClassName { ... }"
        )

    run_id = uuid.uuid4().hex
    work_dir = TEMP_DIR / run_id
    work_dir.mkdir(exist_ok=True)
    source = work_dir / f"{class_name}.java"

    try:
        source.write_text(code, encoding="utf-8")

        compile_proc = _run_command(
            [JAVAC_EXECUTABLE, str(source)],
            work_dir,
            COMPILE_TIMEOUT,
        )
        if compile_proc.returncode != 0:
            return _failure(compile_proc.stderr or "Compilation failed.", compile_proc.stdout)

        run_proc = _run_command(
            [JAVA_EXECUTABLE, class_name],
            work_dir,
            EXECUTION_TIMEOUT,
        )
        if run_proc.returncode == 0:
            return _success(run_proc.stdout)

        return _failure(run_proc.stderr or f"Process exited with code {run_proc.returncode}", run_proc.stdout)

    except subprocess.TimeoutExpired:
        return _failure(f"Execution timed out after {EXECUTION_TIMEOUT} seconds.")
    except FileNotFoundError:
        return _failure(
            f"Java not found. Install JDK with: sudo apt install default-jdk"
        )
    except Exception as exc:
        return _failure(f"Internal error: {exc}")
    finally:
        _cleanup_dir(work_dir)


def extract_java_class_name(code: str) -> str | None:
    match = re.search(r"public\s+class\s+(\w+)", code)
    return match.group(1) if match else None


def _cleanup_stale_sql_sessions() -> None:
    now = time.time()
    stale = [
        sid for sid, entry in SQL_SESSIONS.items()
        if now - entry["last_used"] > SQL_SESSION_TTL
    ]
    for sid in stale:
        try:
            SQL_SESSIONS[sid]["conn"].close()
        except Exception:
            pass
        del SQL_SESSIONS[sid]


def _get_sql_connection(session_id: str) -> sqlite3.Connection:
    with SQL_SESSION_LOCK:
        _cleanup_stale_sql_sessions()
        if session_id not in SQL_SESSIONS:
            conn = sqlite3.connect(":memory:")
            conn.row_factory = sqlite3.Row
            SQL_SESSIONS[session_id] = {"conn": conn, "last_used": time.time()}
        else:
            SQL_SESSIONS[session_id]["last_used"] = time.time()
        return SQL_SESSIONS[session_id]["conn"]


def _split_sql_statements(code: str) -> list[str]:
    """Split SQL on semicolons, ignoring semicolons inside quotes."""
    statements: list[str] = []
    current: list[str] = []
    in_single = False
    in_double = False

    for char in code:
        if char == "'" and not in_double:
            in_single = not in_single
        elif char == '"' and not in_single:
            in_double = not in_double

        if char == ";" and not in_single and not in_double:
            stmt = "".join(current).strip()
            if stmt:
                statements.append(stmt)
            current = []
        else:
            current.append(char)

    tail = "".join(current).strip()
    if tail:
        statements.append(tail)
    return statements


def _strip_sql_comments(statement: str) -> str:
    lines = []
    for line in statement.splitlines():
        stripped = line.strip()
        if stripped.startswith("--"):
            continue
        if "--" in line:
            line = line.split("--", 1)[0]
        lines.append(line)
    return "\n".join(lines).strip()


def _format_sql_table(rows: list[sqlite3.Row], description) -> str:
    if not description:
        return "(empty result set)"

    columns = [col[0] for col in description]
    str_rows = [[str(row[col] if row[col] is not None else "NULL") for col in columns] for row in rows]
    widths = [len(col) for col in columns]
    for row in str_rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(cell))

    separator = "+-" + "-+-".join("-" * w for w in widths) + "-+"
    header = "| " + " | ".join(col.ljust(widths[i]) for i, col in enumerate(columns)) + " |"
    body = [
        "| " + " | ".join(cell.ljust(widths[i]) for i, cell in enumerate(row)) + " |"
        for row in str_rows
    ]

    lines = [separator, header, separator, *body, separator, f"{len(rows)} row(s)"]
    return "\n".join(lines)


def _normalize_create_database(statement: str) -> str | None:
    """Map MySQL-style CREATE DATABASE to SQLite ATTACH, or skip if exists."""
    match = re.match(
        r"CREATE\s+DATABASE\s+(?:IF\s+NOT\s+EXISTS\s+)?([`\"']?\w+[`\"']?)",
        statement,
        re.IGNORECASE,
    )
    if not match:
        return None

    db_name = match.group(1).strip("`\"'")
    if not re.fullmatch(r"\w+", db_name):
        raise sqlite3.OperationalError(f"Invalid database name: {db_name}")
    return f"ATTACH DATABASE ':memory:' AS {db_name}"


def execute_sql(code: str, session_id: str | None) -> dict:
    if not session_id or not isinstance(session_id, str):
        return _failure("SQL requires a session. Refresh the page and try again.")

    if len(session_id) > 64 or not re.fullmatch(r"[\w-]+", session_id):
        return _failure("Invalid session ID.")

    conn = _get_sql_connection(session_id)
    statements = _split_sql_statements(code)
    outputs: list[str] = []

    try:
        for raw in statements:
            statement = _strip_sql_comments(raw)
            if not statement:
                continue

            upper = statement.upper().lstrip()

            if upper.startswith("CREATE DATABASE"):
                statement = _normalize_create_database(statement)
                if statement is None:
                    continue

            if upper.startswith("DROP DATABASE"):
                match = re.match(
                    r"DROP\s+DATABASE\s+(?:IF\s+EXISTS\s+)?([`\"']?\w+[`\"']?)",
                    statement,
                    re.IGNORECASE,
                )
                if match:
                    db_name = match.group(1).strip("`\"'")
                    statement = f"DETACH DATABASE {db_name}"

            cursor = conn.cursor()
            cursor.execute(statement)

            if cursor.description:
                rows = cursor.fetchall()
                outputs.append(_format_sql_table(rows, cursor.description))
            else:
                conn.commit()
                msg = f"Query OK, {cursor.rowcount} row(s) affected"
                if upper.startswith("CREATE TABLE"):
                    match = re.search(
                        r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?([`\"']?\w+[`\"']?)",
                        statement,
                        re.IGNORECASE,
                    )
                    if match:
                        table = match.group(1).strip("`\"'")
                        msg = f"Table '{table}' created successfully."
                elif upper.startswith("INSERT INTO"):
                    msg = f"{cursor.rowcount} row(s) inserted."
                elif upper.startswith("UPDATE"):
                    msg = f"{cursor.rowcount} row(s) updated."
                elif upper.startswith("DELETE FROM"):
                    msg = f"{cursor.rowcount} row(s) deleted."
                elif upper.startswith("CREATE DATABASE") or upper.startswith("ATTACH"):
                    match = re.search(r"\bAS\s+(\w+)", statement, re.IGNORECASE)
                    if match:
                        msg = f"Database '{match.group(1)}' created (in-memory, temporary)."
                outputs.append(msg)

        if not outputs:
            return _success("(No statements to execute)")

        return _success("\n\n".join(outputs))

    except sqlite3.Error as exc:
        return _failure(str(exc))
    except Exception as exc:
        return _failure(f"SQL error: {exc}")


def _cleanup_dir(path: Path) -> None:
    if not path.exists():
        return
    for item in path.iterdir():
        item.unlink(missing_ok=True)
    path.rmdir()


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)

