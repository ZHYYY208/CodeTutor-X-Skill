---
source_id: CUR-PY-101
updated_at: "2026-09-01"
version: "1.0"
course: Python 程序设计基础
language: Python
visibility: all
---

# Python 程序设计基础课程大纲（教学样例）

<!-- chunk_id: sequence-index -->
## 序列与下标

Python 序列下标从 0 开始。长度为 n 的序列，非负合法下标为 0 到 n-1。元素个数与最大合法下标是两个不同概念，应通过手算第一次和最后一次迭代进行区分。

<!-- chunk_id: range-boundary -->
## range 与循环边界

`range(stop)` 生成从 0 到 stop 之前的一系列整数，不包含 stop。分析循环时分别写出首个下标、末个下标和迭代次数，再与序列合法下标比较。

<!-- chunk_id: test-first -->
## 测试先行

修改代码前先保留能暴露问题的最小测试。修复后先重跑同一测试，再补充其他正常与边界测试。预期结果必须注明来自题面推导还是实际执行。
