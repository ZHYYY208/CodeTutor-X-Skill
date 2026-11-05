#!/usr/bin/env python3
import argparse
import csv
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KNOWLEDGE = ROOT / "knowledge"


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


def markdown_records(path, relative, manifest_entry):
    text = path.read_text(encoding="utf-8-sig")
    metadata, body = parse_frontmatter(text)
    marker = re.compile(r"<!--\s*chunk_id:\s*([^\s]+)\s*-->")
    matches = list(marker.finditer(body))
    records = []
    if not matches:
        matches = [None]
    for index, match in enumerate(matches):
        if match is None:
            chunk_id = relative.stem
            content = body.strip()
        else:
            chunk_id = match.group(1)
            end = matches[index + 1].start() if index + 1 < len(matches) else len(body)
            content = body[match.end() : end].strip()
        heading = re.search(r"^#{1,6}\s+(.+)$", content, re.MULTILINE)
        records.append(
            {
                "source_id": metadata.get("source_id", manifest_entry["source_id"]),
                "chunk_id": chunk_id,
                "updated_at": metadata.get("updated_at", manifest_entry.get("updated_at", "未标注")),
                "visibility": metadata.get("visibility", manifest_entry.get("visibility", "all")),
                "language": metadata.get("language", ""),
                "path": relative.as_posix(),
                "title": heading.group(1).strip() if heading else relative.name,
                "text": content,
            }
        )
    return records


def tabular_records(path, relative, manifest_entry, jsonl):
    records = []
    if jsonl:
        rows = []
        for line_number, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
            if line.strip():
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError as exc:
                    raise ValueError(f"{relative}:{line_number} JSONL 无效: {exc.msg}") from exc
    else:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle))
    for index, row in enumerate(rows, 1):
        chunk_id = row.get("chunk_id") or row.get("case_id") or row.get("problem_id") or row.get("variant_id") or row.get("node_id") or row.get("edge_id") or f"row-{index}"
        text = " ".join(str(value) for value in row.values() if value is not None)
        records.append(
            {
                "source_id": row.get("source_id", manifest_entry["source_id"]),
                "chunk_id": chunk_id,
                "updated_at": row.get("updated_at", manifest_entry.get("updated_at", "未标注")),
                "visibility": row.get("visibility", manifest_entry.get("visibility", "all")),
                "language": row.get("language", ""),
                "path": relative.as_posix(),
                "title": row.get("title") or row.get("label") or row.get("case_id") or chunk_id,
                "text": text,
            }
        )
    return records


def visible(record, mode, relative):
    visibility = record["visibility"]
    if visibility == "practice_only" and mode != "practice":
        return False
    if visibility == "exam_review_only" and mode != "exam_review":
        return False
    if mode == "exam_review" and not relative.as_posix().startswith(("curriculum/", "errors/", "graph/", "variants/")):
        return False
    return True


def query_terms(query):
    return [term for term in re.findall(r"[a-zA-Z0-9_+#.-]+|[\u4e00-\u9fff]+", query.lower()) if len(term) > 1]


def score(record, query, terms, language):
    haystack = f"{record['source_id']} {record['chunk_id']} {record['title']} {record['text']}".lower()
    result = 0
    normalized_query = query.lower().strip()
    if normalized_query and normalized_query in haystack:
        result += 6
    for term in terms:
        if term in haystack:
            result += 2
    if language and record["language"].lower() == language.lower():
        result += 2
    return result


def snippet(text, size=420):
    compact = re.sub(r"\s+", " ", text).strip()
    return compact if len(compact) <= size else compact[:size] + "…"


def retrieve(query, mode, language, limit):
    manifest = json.loads((KNOWLEDGE / "manifest.json").read_text(encoding="utf-8"))
    terms = query_terms(query)
    candidates = []
    for entry in manifest["files"]:
        relative = Path(entry["path"])
        path = KNOWLEDGE / relative
        file_format = entry["format"]
        if file_format == "markdown":
            records = markdown_records(path, relative, entry)
        elif file_format in {"csv", "jsonl"}:
            records = tabular_records(path, relative, entry, file_format == "jsonl")
        else:
            continue
        for record in records:
            if not visible(record, mode, relative):
                continue
            record_score = score(record, query, terms, language)
            if record_score > 0:
                record["score"] = record_score
                candidates.append(record)
    candidates.sort(key=lambda item: (-item["score"], item["source_id"], item["chunk_id"]))
    results = [
        {
            "citation": f"{item['source_id']}#{item['chunk_id']}",
            "updated_at": item["updated_at"],
            "path": item["path"],
            "title": item["title"],
            "score": item["score"],
            "snippet": snippet(item["text"]),
        }
        for item in candidates[:limit]
    ]
    return {
        "knowledge_version": manifest["knowledge_version"],
        "mode": mode,
        "query": query,
        "count": len(results),
        "results": results,
    }


def main():
    parser = argparse.ArgumentParser(description="检索 CodeTutor X 本地知识，不执行学生代码。")
    parser.add_argument("query", help="关键词，可用空格分隔，例如：IndexError range")
    parser.add_argument("--mode", choices=["homework", "practice", "exam_review"], default="homework")
    parser.add_argument("--language", default="")
    parser.add_argument("--limit", type=int, default=5)
    args = parser.parse_args()
    try:
        if not args.query.strip() or len(args.query) > 500:
            raise ValueError("query 长度必须为 1–500 字符")
        limit = max(1, min(args.limit, 10))
        output = retrieve(args.query.strip(), args.mode, args.language, limit)
        print(json.dumps(output, ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:
        print(json.dumps({"error": type(exc).__name__, "message": str(exc)}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    sys.exit(main())
