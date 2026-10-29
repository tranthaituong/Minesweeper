"""Compare the same inference task and export raw data, tables, and a report."""
import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import statistics
import sys

from experiments import ROOT, ALGORITHMS, load_cases, run_trials, summarize
from config import ROWS, COLS, MINES


def write_csv(path, rows):
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def report_text(by_input, summary, repeats, metadata):
    lines = [
        "# Minesweeper — Giao diện và thực nghiệm DFS / Hill Climbing", "",
        "## Thiết kế thực nghiệm", "",
        f"Mỗi input là một bàn {ROWS} × {COLS} có {MINES} mìn và một tập ô đã mở sẵn. "
        "Hai thuật toán nhận cùng các số đang hiện, tổng số mìn và cờ. "
        "Nhiệm vụ của mỗi lượt là suy luận một lần từ trạng thái đó: xác định ô an toàn, "
        "ô có mìn và, với Hill Climbing, đề xuất ô đoán nếu có.", "",
        f"Bộ thử gồm {len(by_input)//2} input, mỗi thuật toán lặp {repeats} lần/input. "
        f"Các input có {', '.join(str(n) for n in sorted({r['hidden_cells'] for r in by_input}))} ô ẩn; số ô ẩn biểu thị quy mô đầu vào. "
        "Thời gian và bộ nhớ trong bảng là trung vị các lần lặp.", "",
        "Thời gian đo bằng `time.perf_counter()` trong lúc chạy và thu kết quả solver, "
        "tách khỏi việc mở cửa sổ, dựng input và khởi tạo tiến trình. "
        "Bộ nhớ đo ở một lượt chạy riêng bằng `tracemalloc`: đỉnh bộ nhớ Python "
        "cấp phát cho đối tượng giải, suy luận và lưu kết quả. Đơn vị KiB = 1024 byte. "
        "Đây là bộ nhớ Python của lượt giải, khác với tổng RAM của cả ứng dụng.", "",
        "## Kết quả trên từng input", "",
        "| Input | Ô ẩn | DFS (ms) | HC (ms) | DFS (KiB) | HC (KiB) | An toàn DFS/HC | Mìn DFS/HC | Đoán HC |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    pairs = []
    for case in dict.fromkeys(r["case_id"] for r in by_input):
        d, h = [next(r for r in by_input if r["case_id"] == case and r["algorithm"] == a)
                for a in ALGORITHMS]
        pairs.append((d, h))
        lines.append(f"| {case} | {d['hidden_cells']} | {d['median_planning_ms']:.4f} | "
                     f"{h['median_planning_ms']:.4f} | {d['median_python_peak_kib']:.2f} | "
                     f"{h['median_python_peak_kib']:.2f} | {d['safe_deductions']}/{h['safe_deductions']} | "
                     f"{d['mine_deductions']}/{h['mine_deductions']} | {h['guesses']} |")
    d = next(r for r in summary if r["algorithm"] == "DFS")
    h = next(r for r in summary if r["algorithm"] == "HillClimbing")
    hc_faster = sum(hc["median_planning_ms"] < dfs["median_planning_ms"] for dfs, hc in pairs)
    hc_smaller = sum(hc["median_python_peak_kib"] < dfs["median_python_peak_kib"] for dfs, hc in pairs)
    lines += ["", "## Phân tích", "",
              f"- Trên bộ input này, Hill Climbing nhanh hơn DFS ở {hc_faster}/{len(pairs)} input "
              f"và dùng ít bộ nhớ Python hơn ở {hc_smaller}/{len(pairs)} input.",
              f"- Trung vị toàn bộ lượt chạy: DFS {d['median_planning_ms']:.4f} ms, "
              f"{d['median_python_peak_kib']:.2f} KiB; Hill Climbing {h['median_planning_ms']:.4f} ms, "
              f"{h['median_python_peak_kib']:.2f} KiB.",
              "- Xét tốc độ và bộ nhớ theo từng input; xét khả năng suy luận bằng số ô "
              "an toàn và mìn tìm được. Cột đoán được tách riêng vì đó là đề xuất cần mở ô để kiểm tra.",
              "- Bộ kiểm tra liệt kê các cách đặt mìn phù hợp với số đang hiện để đối chiếu "
              "các kết luận safe/mine. Bước đối chiếu chạy sau khi đo và không cung cấp dữ liệu cho solver.", ""]
    for algorithm in ALGORITHMS:
        cases = [r for r in by_input if r["algorithm"] == algorithm]
        correct = sum(r["deductions_correct"] for r in cases)
        missed = [r["case_id"] for r in cases if r["missed_forced_safe"] or r["missed_forced_mines"]]
        lines.append(f"- {algorithm}: kết luận safe/mine đúng ở {correct}/{len(cases)} input. "
                     + (f"Còn bỏ sót kết luận suy ra được ở {', '.join(missed)}." if missed else
                        "Tìm đủ các kết luận safe/mine suy ra được trên các input đã chạy."))
    lines += ["", "Khi số ô ẩn nhỏ, suy diễn ràng buộc có thể giải quyết phần lớn công việc, "
              "khiến hai thời gian gần nhau. Khi cần duyệt nhiều phép gán, DFS phải tổng hợp "
              "các cấu hình hợp lệ; Hill Climbing của phiên bản đang đo đánh giá nhóm ứng viên "
              "và trả đề xuất theo heuristic. Vì đầu ra có thể khác nhau, đọc các cột kết quả "
              "cùng với cột thời gian để chọn cách xử lý phù hợp.", "",
              "## Cách dùng giao diện để trình bày", "",
              "1. Chọn input T01–T09 bằng hai nút chuyển bàn.",
              "2. Chọn DFS, bấm Step để xem từng hành động; Play/Pause để trình diễn liên tiếp.",
              "3. Bấm Reset: khôi phục đúng các ô mở ban đầu, vị trí mìn và cờ ban đầu.",
              "4. Chọn Hill Climbing và chạy trên cùng input. Lịch sử phân biệt suy luận an toàn, cắm cờ và đoán.",
              "5. Bấm Chạy benchmark để xuất lại bảng thời gian và bộ nhớ.", "",
              "## Thông tin lần chạy", "",
              f"- Mã nguồn gốc: `{metadata['upstream_commit']}`.",
              f"- Python: {metadata['python']}.", f"- Máy chạy: {metadata['platform']}.",
              f"- Thời điểm UTC: {metadata['generated_at_utc']}.",
              "- Mỗi lượt benchmark đo một vòng suy luận; số đo không gồm hoạt ảnh hay thời gian người dùng thao tác.",
              "- Hai file thuật toán giữ nguyên theo mã nguồn gốc; bảng phản ánh phiên bản có mã commit ở trên.", ""]
    return "\n".join(lines)


def run_benchmark(output, seeds=9, repeats=3, start_seed=0, timeout=10):
    cases = load_cases()
    if repeats < 1 or seeds < 1 or not 0 <= start_seed < len(cases) or start_seed+seeds > len(cases):
        raise ValueError(f"Chọn từ 1 đến {len(cases)} input và repeats >= 1.")
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    rows = run_trials(range(start_seed, start_seed+seeds), repeats, timeout,
                      progress=lambda r: print(f"{r['case_id']} {r['algorithm']} lần {r['repeat']}: "
                                               f"{r['planning_ms']:.4f} ms", flush=True))
    write_csv(output / "raw.csv", rows)
    summary = summarize(rows)
    write_csv(output / "summary.csv", summary)
    by_input = []
    for index in range(start_seed, start_seed+seeds):
        for algorithm in ALGORITHMS:
            samples = [r for r in rows if r["case_id"] == cases[index]["id"] and r["algorithm"] == algorithm]
            first = samples[0]
            by_input.append({
                "case_id": first["case_id"], "hidden_cells": first["hidden_cells"],
                "algorithm": algorithm, "repeats": repeats,
                "median_planning_ms": statistics.median(r["planning_ms"] for r in samples),
                "median_python_peak_kib": statistics.median(r["python_peak_kib"] for r in samples),
                "median_expanded_nodes": statistics.median(r["expanded_nodes"] for r in samples),
                "median_generated_nodes": statistics.median(r["generated_nodes"] for r in samples),
                **{key: first[key] for key in ("safe_deductions", "mine_deductions", "guesses",
                                               "guess_hits_mine", "forced_safe_total", "forced_mine_total",
                                               "missed_forced_safe", "missed_forced_mines")},
                "deductions_correct": all(r["deductions_correct"] for r in samples),
            })
    write_csv(output / "by_input.csv", by_input)
    upstream = json.loads((ROOT / "upstream.json").read_text())
    metadata = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "python": sys.version.split()[0], "platform": platform.platform(),
        "upstream_commit": upstream["commit"], "repeats": repeats,
        "cases": [cases[i]["id"] for i in range(start_seed, start_seed+seeds)],
        "task": "one inference round on identical fixed public observations",
        "memory": "tracemalloc peak Python allocations in a separate solver run, KiB",
        "backend_sha256": {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
                           for name in upstream["backend_files"]},
        "inputs_sha256": hashlib.sha256((ROOT / "inputs.json").read_bytes()).hexdigest(),
        "node_units": {"DFS": "consistent recursive assignments / generated binary assignments",
                       "HillClimbing": "simulated candidates / heuristic candidates"},
    }
    (output / "metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    (output / "BAO_CAO_THUC_NGHIEM.md").write_text(report_text(by_input, summary, repeats, metadata), encoding="utf-8")
    return summary


def main():
    parser = argparse.ArgumentParser(description="Đo DFS và Hill Climbing trên cùng các input.")
    parser.add_argument("--cases", "--seeds", dest="cases", type=int, default=9)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--start-seed", type=int, default=0)
    parser.add_argument("--timeout", type=float, default=10)
    parser.add_argument("--output", type=Path, default=ROOT / "benchmark_results")
    args = parser.parse_args()
    if args.timeout <= 0:
        parser.error("--timeout phải lớn hơn 0")
    try:
        result = run_benchmark(args.output, args.cases, args.repeats, args.start_seed, args.timeout)
    except (ValueError, RuntimeError, TimeoutError) as exc:
        raise SystemExit(str(exc))
    for row in result:
        print(f"{row['algorithm']}: {row['median_planning_ms']:.4f} ms; "
              f"{row['median_python_peak_kib']:.2f} KiB", flush=True)
    print(f"Đã lưu bảng và báo cáo: {args.output.resolve()}")


if __name__ == "__main__":
    main()
