# CodeCompiler

A clean, professional online IDE for **Python**, **Java**, and **C**. Write code in the browser, compile and run instantly, and see the output in a polished dark-themed interface.

## Features

- **Three languages** — Python, Java, and C with one-click switching
- **Syntax-highlighted editor** — CodeMirror with auto-close brackets and suggestions
- **Instant execution** — Run code with one click or `Ctrl+Enter`
- **Split-pane layout** — Resizable editor and output panels
- **Per-language samples** — Starter code for each language

## Requirements

| Language | System dependency |
|----------|-------------------|
| Python   | `python3`         |
| C        | `gcc` (build-essential) |
| Java     | `default-jdk` (`javac` + `java`) |

Install on Ubuntu/Debian:

```bash
sudo apt install python3 build-essential default-jdk
```

## Quick Start

```bash
pip install -r requirements.txt
python app.py
```

Open [http://localhost:5000](http://localhost:5000) in your browser.

## Project Structure

```
webui/
├── app.py                  # Flask backend & multi-language execution
├── requirements.txt
├── templates/index.html
└── static/
    ├── css/style.css
    └── js/app.js
```

## API

**POST `/api/run`**

```json
{ "code": "print('Hello')", "language": "python" }
```

Supported `language` values: `python`, `java`, `c`

## Notes

- **Java**: Code must contain a `public class ClassName` — the class name becomes the filename.
- **C**: Compiled with `gcc -Wall`.
- All executions have a 10-second timeout.

## License

MIT
