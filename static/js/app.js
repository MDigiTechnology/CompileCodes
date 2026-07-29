"use strict";

const LANGUAGES = {
  python: {
    mode: "python",
    fileName: "main.py",
    indentUnit: 4,
    defaultCode: `# numpy, pandas, matplotlib, sklearn, openai, etc. are available
print("Hello, World!")
`,
    hints: [
      "False", "None", "True", "and", "as", "assert", "break", "class", "continue",
      "def", "del", "elif", "else", "except", "finally", "for", "from", "global",
      "if", "import", "in", "is", "lambda", "not", "or", "pass", "print", "raise",
      "return", "try", "while", "with", "yield", "len", "range", "int", "float",
      "str", "list", "dict", "set", "tuple", "input", "open", "sum", "min", "max",
      "numpy", "pandas", "matplotlib", "sklearn", "scipy", "seaborn", "openai",
      "torch", "tensorflow", "transformers", "langchain",
    ],
  },
  java: {
    mode: "text/x-java",
    fileName: "Main.java",
    indentUnit: 4,
    defaultCode: `public class Main {
    public static void main(String[] args) {
        System.out.println("Hello, World!");
    }
}
`,
    hints: [
      "public", "class", "static", "void", "main", "String", "int", "double",
      "boolean", "char", "float", "long", "byte", "short", "if", "else", "for",
      "while", "do", "switch", "case", "break", "continue", "return", "new",
      "import", "package", "extends", "implements", "interface", "final",
      "System.out.println", "true", "false", "null",
    ],
  },
  cpp: {
    mode: "text/x-c++src",
    fileName: "main.cpp",
    indentUnit: 4,
    defaultCode: `#include <iostream>
using namespace std;

int main() {
    cout << "Hello, World!" << endl;
    return 0;
}
`,
    hints: [
      "int", "char", "float", "double", "void", "long", "short", "unsigned",
      "if", "else", "for", "while", "do", "switch", "case", "break", "continue",
      "return", "struct", "class", "namespace", "std", "cout", "cin", "endl",
      "vector", "string", "include", "iostream", "main", "nullptr", "auto",
    ],
  },
  sql: {
    mode: "text/x-sql",
    fileName: "query.sql",
    indentUnit: 2,
    runLabel: "Run Query",
    defaultCode: `-- Temporary in-memory database (resets on page refresh)
CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT);
INSERT INTO users (name) VALUES ('Alice'), ('Bob');
SELECT * FROM users;
`,
    hints: [
      "SELECT", "FROM", "WHERE", "INSERT", "INTO", "VALUES", "UPDATE", "SET",
      "DELETE", "CREATE", "TABLE", "DATABASE", "DROP", "ALTER", "JOIN",
      "INNER", "LEFT", "RIGHT", "ON", "GROUP", "BY", "ORDER", "HAVING",
      "LIMIT", "DISTINCT", "AS", "AND", "OR", "NOT", "NULL", "PRIMARY",
      "KEY", "FOREIGN", "REFERENCES", "INTEGER", "TEXT", "REAL", "BLOB",
      "AUTOINCREMENT", "UNIQUE", "DEFAULT", "COUNT", "SUM", "AVG", "MAX", "MIN",
    ],
  },
};

document.addEventListener("DOMContentLoaded", () => {
  const initialLang =
    typeof window.DEFAULT_COMPILER_LANG === "string" &&
    Object.prototype.hasOwnProperty.call(LANGUAGES, window.DEFAULT_COMPILER_LANG)
      ? window.DEFAULT_COMPILER_LANG
      : "python";
  let currentLang = initialLang;
  const codeCache = {};
  const sqlSessionId = crypto.randomUUID();

  const editor = CodeMirror.fromTextArea(document.getElementById("code-editor"), {
    mode: LANGUAGES[initialLang].mode,
    theme: "dracula",
    lineNumbers: true,
    indentUnit: 4,
    tabSize: 4,
    indentWithTabs: false,
    lineWrapping: true,
    autofocus: true,
    autoCloseBrackets: {
      pairs: "()[]{}''\"\"",
      closeBefore: ")]}':;>",
      triples: "''\"\"",
      explode: "[]{}",
    },
    matchBrackets: true,
    extraKeys: {
      Tab: (cm) => {
        if (cm.state.completionActive) return CodeMirror.Pass;
        if (cm.somethingSelected()) {
          cm.indentSelection("add");
        } else {
          cm.replaceSelection("    ", "end");
        }
      },
      "Ctrl-Space": "autocomplete",
      "Ctrl-Enter": () => runCode(),
      "Cmd-Enter": () => runCode(),
    },
    hintOptions: { hint: codeHint },
  });

  const outputEl = document.getElementById("output");
  const statusDot = document.getElementById("status-dot");
  const lineInfo = document.getElementById("line-info");
  const fileNameEl = document.getElementById("file-name");
  const btnRun = document.getElementById("btn-run");
  const btnClear = document.getElementById("btn-clear");
  const langTabs = document.querySelectorAll(".lang-tab");
  const sqlNotice = document.getElementById("sql-notice");
  const RUN_BTN_ICON = `<svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor"><path d="m11.596 8.697-6.363 3.692c-.54.313-1.233-.066-1.233-.697V4.308c0-.63.692-1.01 1.233-.696l6.363 3.692a.802.802 0 0 1 0 1.393z"/></svg>`;
  const RUNNING_BTN_ICON = `<svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor"><path d="M8 3a5 5 0 1 0 4.546 2.914.5.5 0 0 1 .908-.417A6 6 0 1 1 8 2v1z"/><path d="M8 4.466V.534a.25.25 0 0 1 .41-.192l2.36 1.966c.12.1.12.284 0 .384L8.41 4.658A.25.25 0 0 1 8 4.466z"/></svg>`;

  editor.setValue(LANGUAGES[initialLang].defaultCode);
  codeCache[initialLang] = LANGUAGES[initialLang].defaultCode;
  langTabs.forEach((tab) => {
    tab.classList.toggle("active", tab.dataset.lang === initialLang);
  });
  fileNameEl.textContent = LANGUAGES[initialLang].fileName;
  sqlNotice.classList.toggle("hidden", initialLang !== "sql");
  updateRunButtonLabel(LANGUAGES[initialLang].runLabel || "Run");

  editor.on("cursorActivity", () => {
    const cursor = editor.getCursor();
    lineInfo.textContent = `Ln ${cursor.line + 1}, Col ${cursor.ch + 1}`;
  });

  editor.on("inputRead", (cm, change) => {
    if (change.origin !== "+input") return;
    const typed = change.text[0];
    if (/^[a-zA-Z_.]$/.test(typed)) {
      CodeMirror.commands.autocomplete(cm, null, { completeSingle: false });
    }
  });

  langTabs.forEach((tab) => {
    tab.addEventListener("click", () => switchLanguage(tab.dataset.lang));
  });

  btnRun.addEventListener("click", runCode);

  btnClear.addEventListener("click", () => {
    editor.setValue("");
    editor.focus();
    resetOutput();
  });

  document.addEventListener("keydown", (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
      e.preventDefault();
      runCode();
    }
  });

  initDivider();

  let isRunning = false;

  function switchLanguage(lang) {
    if (lang === currentLang) return;

    codeCache[currentLang] = editor.getValue();
    currentLang = lang;

    langTabs.forEach((tab) => {
      tab.classList.toggle("active", tab.dataset.lang === lang);
    });

    const config = LANGUAGES[lang];
    editor.setOption("mode", config.mode);
    editor.setOption("indentUnit", config.indentUnit);
    editor.setOption("tabSize", config.indentUnit);
    fileNameEl.textContent = config.fileName;

    sqlNotice.classList.toggle("hidden", lang !== "sql");
    updateRunButtonLabel(config.runLabel || "Run");

    editor.setValue(codeCache[lang] ?? config.defaultCode);
    editor.focus();
    resetOutput(lang);
  }

  function updateRunButtonLabel(label) {
    if (btnRun.classList.contains("running")) return;
    btnRun.innerHTML = `${RUN_BTN_ICON}\n${label}`;
  }

  async function runCode() {
    if (isRunning) return;

    const code = editor.getValue();
    if (!code.trim()) {
      showOutput("Please write some code before running.", "error");
      return;
    }

    isRunning = true;
    btnRun.disabled = true;
    btnRun.classList.add("running");
    btnRun.innerHTML = `${RUNNING_BTN_ICON}\nRunning...`;
    setStatus("running");
    const runningLabel = currentLang === "sql" ? "Running query..." : "Compiling and executing...";
    showOutput(runningLabel, "");

    try {
      const payload = { code, language: currentLang };
      if (currentLang === "sql") {
        payload.session_id = sqlSessionId;
      }

      const response = await fetch("/api/run", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      const data = await response.json();

      if (data.success) {
        showOutput(data.output, "success");
        setStatus("success");
      } else {
        const message = [data.error, data.output].filter(Boolean).join("\n");
        showOutput(message, "error");
        setStatus("error");
      }
    } catch (err) {
      showOutput(`Network error: ${err.message}`, "error");
      setStatus("error");
    } finally {
      isRunning = false;
      btnRun.disabled = false;
      btnRun.classList.remove("running");
      updateRunButtonLabel(LANGUAGES[currentLang].runLabel || "Run");
    }
  }

  function showOutput(text, type) {
    outputEl.textContent = text;
    outputEl.className = "output-content";
    if (type) outputEl.classList.add(type);
    if (text && type !== "error") outputEl.classList.add("has-output");
  }

  function resetOutput(lang = currentLang) {
    const readyText = lang === "sql"
      ? "Ready. Write SQL queries and click Run Query. Data is temporary until you refresh."
      : "Ready. Press Ctrl+Enter or click Run to execute.";
    outputEl.textContent = readyText;
    outputEl.className = "output-content";
    setStatus("");
  }

  function setStatus(state) {
    statusDot.className = "status-dot";
    if (state) statusDot.classList.add(state);
  }

  function codeHint(cm) {
    const cursor = cm.getCursor();
    const line = cm.getLine(cursor.line);

    let end = cursor.ch;
    while (end < line.length && /[\w.]/.test(line.charAt(end))) end++;
    let wordStart = cursor.ch;
    while (wordStart > 0 && /[\w.]/.test(line.charAt(wordStart - 1))) wordStart--;

    const word = line.slice(wordStart, end).toLowerCase();
    const docWords = new Set();

    for (let i = 0; i < cm.lineCount(); i++) {
      const tokens = cm.getLine(i).match(/[a-zA-Z_]\w*/g);
      if (tokens) tokens.forEach((t) => docWords.add(t));
    }

    const langHints = LANGUAGES[currentLang].hints;
    const all = [...langHints, ...docWords];
    const matches = all.filter(
      (item) => item.toLowerCase().startsWith(word) && item.toLowerCase() !== word
    );

    return {
      list: [...new Set(matches)].sort().slice(0, 20),
      from: CodeMirror.Pos(cursor.line, wordStart),
      to: CodeMirror.Pos(cursor.line, end),
    };
  }

  function initDivider() {
    const divider = document.getElementById("divider");
    const editorPanel = document.querySelector(".editor-panel");
    const outputPanel = document.querySelector(".output-panel");
    const workspace = document.querySelector(".workspace");
    let isDragging = false;

    const isVerticalLayout = () =>
      window.matchMedia("(max-width: 768px)").matches;

    divider.addEventListener("mousedown", (e) => {
      isDragging = true;
      divider.classList.add("active");
      document.body.style.cursor = isVerticalLayout() ? "row-resize" : "col-resize";
      document.body.style.userSelect = "none";
      e.preventDefault();
    });

    divider.addEventListener("touchstart", (e) => {
      isDragging = true;
      divider.classList.add("active");
      document.body.style.userSelect = "none";
      e.preventDefault();
    }, { passive: false });

    const handleMove = (clientX, clientY) => {
      if (!isDragging) return;

      const rect = workspace.getBoundingClientRect();

      if (isVerticalLayout()) {
        const ratio = (clientY - rect.top) / rect.height;
        const clamped = Math.min(Math.max(ratio, 0.2), 0.8);
        editorPanel.style.flex = `1 1 ${clamped * 100}%`;
        outputPanel.style.flex = `1 1 ${(1 - clamped) * 100}%`;
      } else {
        const ratio = (clientX - rect.left) / rect.width;
        const clamped = Math.min(Math.max(ratio, 0.2), 0.8);
        editorPanel.style.flex = `1 1 ${clamped * 100}%`;
        outputPanel.style.flex = `1 1 ${(1 - clamped) * 100}%`;
      }

      editor.refresh();
    };

    document.addEventListener("mousemove", (e) => {
      handleMove(e.clientX, e.clientY);
    });

    document.addEventListener("touchmove", (e) => {
      if (!isDragging || !e.touches.length) return;
      handleMove(e.touches[0].clientX, e.touches[0].clientY);
    }, { passive: true });

    const stopDrag = () => {
      if (!isDragging) return;
      isDragging = false;
      divider.classList.remove("active");
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
    };

    document.addEventListener("mouseup", stopDrag);
    document.addEventListener("touchend", stopDrag);
  }
});
