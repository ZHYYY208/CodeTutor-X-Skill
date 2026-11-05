#!/usr/bin/env python3
import csv
import json
import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KNOWLEDGE = ROOT / "knowledge"
TEXT_SUFFIXES = {".md", ".json", ".jsonl", ".csv", ".yaml", ".py"}


def parse_frontmatter(text):
    if not text.startswith("---\n"):
        return {}, text
    end = text.find("\n---\n", 4)
    if end == -1:
        return {}, text
    metadata = {}
    for line in text[4:end].splitlines():
        if ":" in line:
            key, value = line.split(":", 1)
            metadata[key.strip()] = value.strip().strip('"').strip("'")
    return metadata, text[end + 5 :]


def valid_date(value):
    try:
        date.fromisoformat(value)
        return True
    except (TypeError, ValueError):
        return False


def main():
    errors = []
    warnings = []
    record_count = 0

    def error(message):
        errors.append(message)

    try:
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        metadata, body = parse_frontmatter(skill)
        if not re.fullmatch(r"[a-z0-9-]+", metadata.get("name", "")):
            error("SKILL.md name 缺失或不是 hyphen-case")
        if metadata.get("name") != ROOT.name:
            error("SKILL.md name 必须与目录名一致")
        description = metadata.get("description", "")
        if not description or len(description) > 1024:
            error("SKILL.md description 缺失或超过 1024 字符")
        if len(body.splitlines()) >= 500:
            error("SKILL.md 正文必须少于 500 行")
    except Exception as exc:
        error(f"SKILL.md 无法读取: {exc}")

    for required in ["README.md", "prompts/manifest.json", "workflows/state_schema.json", "evaluation/golden_cases.csv"]:
        if not (ROOT / required).is_file():
            error(f"缺少文件: {required}")

    for path in ROOT.rglob("*"):
        if path.is_file() and path.suffix in TEXT_SUFFIXES:
            text = path.read_text(encoding="utf-8-sig")
            if "TO" + "DO:" in text:
                error(f"存在未完成标记: {path.relative_to(ROOT)}")

    try:
        prompts = json.loads((ROOT / "prompts/manifest.json").read_text(encoding="utf-8"))
        if not prompts.get("prompts"):
            error("prompts/manifest.json 缺少 prompts")
        json.loads((ROOT / "workflows/state_schema.json").read_text(encoding="utf-8"))
    except Exception as exc:
        error(f"提示词或状态清单无效: {exc}")

    try:
        with (ROOT / "evaluation/golden_cases.csv").open("r", encoding="utf-8-sig", newline="") as handle:
            cases = list(csv.DictReader(handle))
        if len(cases) < 10:
            warnings.append("golden cases 少于 10 条")
    except Exception as exc:
        error(f"golden_cases.csv 无效: {exc}")

    try:
        manifest = json.loads((KNOWLEDGE / "manifest.json").read_text(encoding="utf-8"))
        entries = manifest["files"]
        seen_paths = set()
        for entry in entries:
            relative = Path(entry["path"])
            if relative.as_posix() in seen_paths:
                error(f"manifest 路径重复: {relative}")
            seen_paths.add(relative.as_posix())
            path = (KNOWLEDGE / relative).resolve()
            try:
                path.relative_to(KNOWLEDGE.resolve())
            except ValueError:
                error(f"知识路径越界: {relative}")
                continue
            if not path.is_file():
                error(f"知识文件不存在: {relative}")
                continue
            if not valid_date(entry.get("updated_at")):
                error(f"manifest 日期无效: {relative}")
            file_format = entry.get("format")
            if file_format == "markdown":
                metadata, body = parse_frontmatter(path.read_text(encoding="utf-8-sig"))
                for field in ["source_id", "updated_at", "visibility"]:
                    if not metadata.get(field):
                        error(f"{relative} 缺少 {field}")
                if metadata.get("updated_at") and not valid_date(metadata["updated_at"]):
                    error(f"{relative} frontmatter 日期无效")
                chunks = re.findall(r"<!--\s*chunk_id:\s*([^\s]+)\s*-->", body)
                if not chunks:
                    error(f"{relative} 缺少 chunk_id")
                if len(chunks) != len(set(chunks)):
                    error(f"{relative} chunk_id 重复")
                record_count += max(1, len(chunks))
            elif file_format == "jsonl":
                seen_ids = set()
                for line_number, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
                    if not line.strip():
                        continue
                    try:
                        row = json.loads(line)
                    except json.JSONDecodeError as exc:
                        error(f"{relative}:{line_number} JSONL 无效: {exc.msg}")
                        continue
                    for field in ["source_id", "chunk_id", "updated_at", "visibility"]:
                        if not row.get(field):
                            error(f"{relative}:{line_number} 缺少 {field}")
                    if row.get("updated_at") and not valid_date(row["updated_at"]):
                        error(f"{relative}:{line_number} 日期无效")
                    if row.get("chunk_id") in seen_ids:
                        error(f"{relative}:{line_number} chunk_id 重复")
                    seen_ids.add(row.get("chunk_id"))
                    record_count += 1
            elif file_format == "csv":
                with path.open("r", encoding="utf-8-sig", newline="") as handle:
                    rows = list(csv.DictReader(handle))
                for row_number, row in enumerate(rows, 2):
                    for field in ["source_id", "updated_at", "visibility"]:
                        if not row.get(field):
                            error(f"{relative}:{row_number} 缺少 {field}")
                    if row.get("updated_at") and not valid_date(row["updated_at"]):
                        error(f"{relative}:{row_number} 日期无效")
                    record_count += 1
            else:
                error(f"不支持的知识格式: {relative} {file_format}")

            content = path.read_text(encoding="utf-8-sig")
            if re.search(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----", content):
                error(f"知识文件疑似包含私钥: {relative}")
            if re.search(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b", content):
                warnings.append(f"知识文件疑似包含邮箱，请人工确认脱敏: {relative}")
    except Exception as exc:
        error(f"知识库校验失败: {exc}")

    output = {
        "pass": not errors,
        "skill": ROOT.name,
        "knowledge_files": len(seen_paths) if "seen_paths" in locals() else 0,
        "knowledge_records": record_count,
        "errors": errors,
        "warnings": warnings,
        "note": "敏感信息扫描仅作辅助，公开前仍需人工复核。",
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(json.dumps({"pass": False, "error": type(exc).__name__, "message": str(exc)}, ensure_ascii=False))
        sys.exit(1)
