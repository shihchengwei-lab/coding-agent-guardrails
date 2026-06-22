import difflib
import json
import re
from dataclasses import dataclass
from pathlib import Path


DEPENDENCY_FILES = {
    "requirements.txt",
    "pyproject.toml",
    "package.json",
    "package-lock.json",
    "pnpm-lock.yaml",
    "yarn.lock",
}


@dataclass(frozen=True)
class RawResult:
    public_passed: bool
    hidden_passed: bool
    changed_files: list[str]
    line_delta: int
    dependency_incidents: int
    quality_hits: int
    quality_total: int


@dataclass(frozen=True)
class Score:
    capability: float
    discipline: float
    total: float


@dataclass(frozen=True)
class DiffStats:
    changed_files: list[str]
    line_delta: int


@dataclass(frozen=True)
class CalibrationVerdict:
    ok: bool
    reasons: list[str]


def score_result(result: RawResult, max_files: int, max_line_delta: int) -> Score:
    capability = _capability_score(result.public_passed, result.hidden_passed)
    discipline = _discipline_score(result, max_files, max_line_delta)
    total = round((capability * 0.70) + (discipline * 0.30), 2)
    return Score(capability=capability, discipline=discipline, total=total)


def diff_stats(before: Path, after: Path, ignored_paths: set[str] | None = None) -> DiffStats:
    changed_files = []
    line_delta = 0
    ignored_paths = ignored_paths or set()

    for relative_path in sorted(_relative_files(before) | _relative_files(after)):
        if relative_path.as_posix() in ignored_paths:
            continue
        before_lines = _read_lines(before / relative_path)
        after_lines = _read_lines(after / relative_path)
        if before_lines == after_lines:
            continue
        changed_files.append(relative_path.as_posix())
        line_delta += _line_delta(before_lines, after_lines)

    return DiffStats(changed_files=changed_files, line_delta=line_delta)


def dependency_incidents(before: Path, after: Path, changed_files: list[str]) -> int:
    before_names = _dependency_names(before)
    after_names = _dependency_names(after)
    new_dependencies = after_names - before_names
    changed_dependency_files = [
        path for path in changed_files if Path(path).name in DEPENDENCY_FILES
    ]
    if new_dependencies:
        return len(new_dependencies)
    return len(changed_dependency_files)


def calibration_verdict(summary: dict[str, float]) -> CalibrationVerdict:
    reasons = []
    frontier = summary.get("gpt-5.5")
    strong = summary.get("gpt-5.4")
    mini = summary.get("gpt-5.4-mini")
    spark = summary.get("gpt-5.3-codex-spark")

    if spark is not None and mini is not None and spark > mini:
        reasons.append("spark baseline is above mini")
    if spark is not None and frontier is not None and spark > frontier:
        reasons.append("spark baseline is above frontier")
    if mini is not None and strong is not None and mini > strong:
        reasons.append("mini baseline is above strong")
    if strong is not None and frontier is not None and strong > frontier + 5:
        reasons.append("strong baseline is far above frontier")

    return CalibrationVerdict(ok=not reasons, reasons=reasons)


def _capability_score(public_passed: bool, hidden_passed: bool) -> float:
    public = 35.0 if public_passed else 0.0
    hidden = 65.0 if hidden_passed else 0.0
    return public + hidden


def _discipline_score(result: RawResult, max_files: int, max_line_delta: int) -> float:
    file_score = 100.0 if len(result.changed_files) <= max_files else 45.0
    if max_line_delta <= 0:
        line_score = 100.0 if result.line_delta == 0 else 0.0
    elif result.line_delta <= max_line_delta:
        line_score = 100.0
    else:
        line_score = max(0.0, 100.0 - ((result.line_delta - max_line_delta) / max_line_delta * 100.0))

    dependency_score = 100.0 if result.dependency_incidents == 0 else 0.0
    quality_score = 100.0
    if result.quality_total:
        quality_score = result.quality_hits / result.quality_total * 100.0

    return round(
        (file_score * 0.25)
        + (line_score * 0.25)
        + (dependency_score * 0.25)
        + (quality_score * 0.25),
        2,
    )


def _relative_files(root: Path) -> set[Path]:
    if not root.exists():
        return set()
    return {
        path.relative_to(root)
        for path in root.rglob("*")
        if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc"
    }


def _read_lines(path: Path) -> list[str]:
    if not path.exists():
        return []
    return path.read_text(encoding="utf-8").splitlines(keepends=True)


def _line_delta(before_lines: list[str], after_lines: list[str]) -> int:
    return sum(
        1
        for line in difflib.ndiff(before_lines, after_lines)
        if line.startswith("- ") or line.startswith("+ ")
    )


def _dependency_names(root: Path) -> set[str]:
    return _requirements_names(root / "requirements.txt") | _package_json_names(root / "package.json")


def _requirements_names(path: Path) -> set[str]:
    if not path.exists():
        return set()
    names = set()
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if not line or line.startswith("-"):
            continue
        name = re.split(r"[<>=!~\[]", line, maxsplit=1)[0].strip()
        if name:
            names.add(name.lower())
    return names


def _package_json_names(path: Path) -> set[str]:
    if not path.exists():
        return set()
    data = json.loads(path.read_text(encoding="utf-8"))
    names = set()
    for section in ("dependencies", "devDependencies", "peerDependencies"):
        names.update(name.lower() for name in data.get(section, {}))
    return names
