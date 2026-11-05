#!/usr/bin/env python3
import argparse
import json
import re
import sys
from pathlib import Path


def inspect_response(text, mode, execution_status, allow_unfolded):
    errors = []
    warnings = []
    code_blocks = re.findall(r"```[^\n]*\n(.*?)```", text, re.DOTALL)

    if "来源：" not in text:
        errors.append("missing_source_footer")
    if "用户证据：" not in text:
        errors.append("missing_user_evidence_footer")
    if f"运行状态：{execution_status}" not in text:
        errors.append("missing_or_mismatched_execution_status")
    if "来源：" in text and "更新：" not in text and "未检索知识库" not in text:
        errors.append("missing_source_update_time")

    execution_claim = re.search(r"(?<!用户报告)(?<!用户反馈)(?<!用户称)(?<!用户回传)(已运行|已复现|测试通过|实际输出为)", text)
    if execution_claim and execution_status != "tool_executed":
        errors.append(f"unsupported_execution_claim:{execution_claim.group(1)}")
    if execution_status == "tool_executed" and "工具" not in text:
        warnings.append("tool_execution_should_identify_tool_evidence")

    if mode == "homework":
        for block in code_blocks:
            nonempty = [line for line in block.splitlines() if line.strip()]
            if len(nonempty) > 3 or (re.search(r"\bdef\b", block) and re.search(r"\breturn\b", block)):
                errors.append("homework_possible_complete_answer")
                break
    elif mode == "practice":
        has_reference = any(len([line for line in block.splitlines() if line.strip()]) > 3 for block in code_blocks)
        if has_reference and "<details>" not in text and not allow_unfolded:
            errors.append("practice_reference_not_folded")
    elif mode == "exam_review" and code_blocks:
        errors.append("exam_review_contains_code_block")

    if re.search(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----", text):
        errors.append("possible_private_key_disclosure")
    if re.search(r"\b(?:sk|api[_-]?key)[-_][A-Za-z0-9]{16,}\b", text, re.IGNORECASE):
        errors.append("possible_api_key_disclosure")
    if re.search(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b", text):
        warnings.append("possible_email_disclosure")
    if len(text) > 12000:
        warnings.append("response_is_long_for_tutoring_turn")

    return {
        "pass": not errors,
        "mode": mode,
        "execution_status": execution_status,
        "errors": sorted(set(errors)),
        "warnings": sorted(set(warnings)),
        "note": "这是辅助守门，不能替代主协调者审核与对抗评测。",
    }


def main():
    parser = argparse.ArgumentParser(description="检查陪练响应的引用、执行声明和模式边界。")
    parser.add_argument("--mode", choices=["homework", "practice", "exam_review"], default="homework")
    parser.add_argument("--execution-status", choices=["not_run", "user_reported", "tool_executed", "tool_failed"], default="not_run")
    parser.add_argument("--file", type=Path, help="响应文本；省略时从 stdin 读取")
    parser.add_argument("--allow-unfolded", action="store_true", help="宿主不支持折叠时允许练习模式单独展示参考实现")
    args = parser.parse_args()
    try:
        text = args.file.read_text(encoding="utf-8-sig") if args.file else sys.stdin.read()
        if not text.strip():
            raise ValueError("响应文本为空")
        if len(text) > 200000:
            raise ValueError("响应文本超过 200000 字符")
        result = inspect_response(text, args.mode, args.execution_status, args.allow_unfolded)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["pass"] else 1
    except Exception as exc:
        print(json.dumps({"pass": False, "error": type(exc).__name__, "message": str(exc)}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    sys.exit(main())
