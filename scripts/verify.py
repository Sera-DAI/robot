#!/usr/bin/env python3
"""Local and CI verification.

--quick : architecture rules (Lambda and agent), secret scan and the domain tests.
--full  : the same, with all tests.

Exits non-zero if any check fails.
"""
from __future__ import annotations

import argparse
import ast
import re
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOMAIN = ROOT / "lambda" / "robot_lambda" / "domain"
TESTS = ROOT / "lambda" / "tests"
LAMBDA_CODE = ROOT / "lambda"
AGENT_CODE = ROOT / "agent"
AGENT = AGENT_CODE / "robot_agent"
AGENT_DOMAIN = AGENT / "domain"
AGENT_TESTS = AGENT_CODE / "tests_agent"
# Test folders with different names: two folders called "tests" would collide in the same process.
SUITES = [(TESTS, LAMBDA_CODE), (AGENT_TESTS, AGENT_CODE)]

# In the agent, only this file may run a process. It runs with the power to shut the PC down.
AGENT_EXECUTOR = "adapters/shutdown.py"
EXECUTION_MODULES = {"subprocess", "pty", "pexpect", "multiprocessing"}
FORBIDDEN_FUNCTIONS_IN_AGENT = {"eval", "exec", "compile", "__import__"}  # called by name
FORBIDDEN_METHODS_IN_AGENT = {  # called as an attribute, for example os.system
    "system", "popen", "startfile",
    "execv", "execve", "execl", "execle", "execlp", "execlpe", "execvp", "execvpe",
    "spawnl", "spawnle", "spawnlp", "spawnlpe", "spawnv", "spawnve", "spawnvp", "spawnvpe",
    "posix_spawn", "posix_spawnp", "fork", "ShellExecuteW", "WinExec", "CreateProcessW", "CreateProcessA",
}
# ctypes gives access to the whole Windows API: only the Credential Manager module may use it.
CTYPES_FILE = "adapters/credentials.py"
AGENT_PACKAGE = "robot_agent"

# The domain is pure: no I/O and no dependency on the adapters.
FORBIDDEN_IMPORTS_IN_DOMAIN = {
    "boto3", "botocore", "urllib", "http", "requests", "socket", "subprocess",
    "os", "shutil", "pathlib", "ssl", "ctypes", "robot_lambda.adapters", "adapters",
}

EMAIL_OK = ("noreply", "example.")
FICTIONAL_MACS = {"00-14-22-01-23-45"}
TEXT_EXTENSIONS = {
    ".py", ".md", ".yml", ".yaml", ".json", ".toml", ".txt", ".ps1", ".cfg", ".ini", ".gitignore",
}

SECRET_PATTERNS = [
    ("AWS access key", re.compile(r"\bA(?:KIA|SIA)[0-9A-Z]{16}\b")),
    ("LWA client id", re.compile(r"amzn1\.application-oa2-client\.[0-9a-f]{32}")),
    ("Alexa skill id", re.compile(r"amzn1\.ask\.skill\.[0-9a-f-]{36}")),
    ("LWA token", re.compile(r"\bAtz[ra]\|[A-Za-z0-9_\-]{20,}")),
    ("private key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("local Windows path", re.compile(r"\b[A-Za-z]:\\Users\\")),
    ("local Linux path", re.compile(r"(?<![\w.])/home/[A-Za-z]")),
    ("email", re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")),
    ("MAC address", re.compile(r"\b(?:[0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}\b")),
]


def _imported_modules(code: str) -> set[str]:
    tree = ast.parse(code)
    found: set[str] = set()
    for no in ast.walk(tree):
        if isinstance(no, ast.Import):
            found.update(a.name for a in no.names)
        elif isinstance(no, ast.ImportFrom):
            base = ("." * no.level) + (no.module or "")
            found.add(base)
            found.update(f"{base}.{a.name}" for a in no.names)
    return found


def check_dependencies(folder: Path) -> list[str]:
    """Forbidden-import errors in the domain files."""
    errors: list[str] = []
    if not folder.exists():
        return errors
    for file in sorted(folder.rglob("*.py")):
        for module in _imported_modules(file.read_text(encoding="utf-8")):
            clean = module.lstrip(".")
            top = clean.split(".")[0]
            if clean in FORBIDDEN_IMPORTS_IN_DOMAIN or top in FORBIDDEN_IMPORTS_IN_DOMAIN:
                errors.append(f"{file}: the domain cannot import '{module}'")
            elif "adapters" in clean.split("."):
                errors.append(f"{file}: the domain cannot import '{module}'")
    return errors


def check_agent(folder: Path) -> list[str]:
    """Process-execution or dynamic-code errors outside the agent's only executor."""
    errors: list[str] = []
    if not folder.exists():
        return errors
    for file in sorted(folder.rglob("*.py")):
        tree = ast.parse(file.read_text(encoding="utf-8"))
        is_executor = file.relative_to(folder).as_posix() == AGENT_EXECUTOR
        relative = file.relative_to(folder).as_posix()
        for module in _imported_modules(ast.unparse(tree)):
            top = module.lstrip(".").split(".")[0]
            if top in EXECUTION_MODULES and not is_executor:
                errors.append(f"{file}: only {AGENT_EXECUTOR} may import '{module}'")
            elif top == "ctypes" and relative != CTYPES_FILE:
                errors.append(f"{file}: only {CTYPES_FILE} may import '{module}'")
            elif not module.startswith(".") and top != AGENT_PACKAGE and top not in sys.stdlib_module_names:
                errors.append(f"{file}: the agent uses only the standard library, not '{module}'")
            if module.split(".")[-1] in FORBIDDEN_METHODS_IN_AGENT:
                errors.append(f"{file}: forbidden import in the agent: '{module}'")
        for no in ast.walk(tree):
            if isinstance(no, ast.Call):
                target = no.func
                name = ""
                if isinstance(target, ast.Name) and target.id in FORBIDDEN_FUNCTIONS_IN_AGENT | FORBIDDEN_METHODS_IN_AGENT:
                    name = target.id
                elif isinstance(target, ast.Attribute) and target.attr in FORBIDDEN_METHODS_IN_AGENT:
                    name = target.attr
                if name:
                    errors.append(f"{file}:{no.lineno}: forbidden call in the agent: '{name}'")
                for argument in no.keywords:
                    if argument.arg is None:
                        errors.append(f"{file}:{no.lineno}: the agent never passes ** arguments in calls")
                    elif argument.arg == "shell" and not (
                        isinstance(argument.value, ast.Constant) and argument.value.value is False
                    ):
                        errors.append(f"{file}:{no.lineno}: the agent never uses shell")
    return errors


def _tracked_files(raiz: Path) -> list[Path]:
    try:
        output = subprocess.run(
            ["git", "-C", str(raiz), "ls-files", "-co", "--exclude-standard"],
            check=True, capture_output=True, text=True,
        ).stdout.splitlines()
        return [raiz / line for line in output if line]
    except (OSError, subprocess.CalledProcessError):
        return [p for p in raiz.rglob("*") if p.is_file() and ".git" not in p.parts]


def check_secrets(raiz: Path, files: list[Path] | None = None) -> list[str]:
    """Sensitive-data errors in text files. Never prints the value found."""
    errors: list[str] = []
    for file in files if files is not None else _tracked_files(raiz):
        if file.suffix.lower() not in TEXT_EXTENSIONS or not file.is_file():
            continue
        try:
            lines = file.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeDecodeError):
            continue
        for number, line in enumerate(lines, start=1):
            for name, pattern in SECRET_PATTERNS:
                for match in pattern.finditer(line):
                    text = match.group(0)
                    if name == "email" and any(ok in text.lower() for ok in EMAIL_OK):
                        continue
                    if name == "MAC address" and text.lower() in FICTIONAL_MACS:
                        continue
                    errors.append(f"{file}:{number}: possible {name}")
    return errors


def _run_tests(pattern: str) -> bool:
    all_ok = True
    for folder, top in SUITES:
        if not folder.exists():
            print(f"FAILURE: missing test folder {folder}")
            all_ok = False
            continue
        sys.path.insert(0, str(top))
        suite = unittest.defaultTestLoader.discover(str(folder), pattern=pattern, top_level_dir=str(top))
        if suite.countTestCases() == 0:
            print(f"FAILURE: no tests found in {folder}")
            all_ok = False
        elif not unittest.TextTestRunner(verbosity=1).run(suite).wasSuccessful():
            all_ok = False
    return all_ok


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--quick", action="store_true")
    mode.add_argument("--full", action="store_true")
    args = parser.parse_args(argv)

    failures: list[str] = []
    failures += check_dependencies(DOMAIN)
    failures += check_dependencies(AGENT_DOMAIN)
    failures += check_agent(AGENT)
    failures += check_secrets(ROOT)
    for failure in failures:
        print(f"FAILURE: {failure}")

    pattern = "test_*.py" if args.full else "test_domain*.py"
    tests_ok = _run_tests(pattern)
    if failures or not tests_ok:
        print("verification failed")
        return 1
    print("verification passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
