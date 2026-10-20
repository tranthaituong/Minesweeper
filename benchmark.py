"""Run benchmark: python benchmark.py --seeds 10 --repeats 3"""

import argparse
import csv
import json
from pathlib import Path
import statistics

from experiments import run_trials, summarize


def run_benchmark(output, seeds=10, repeats=3, start_seed=0):
    """Chạy benchmark và lưu kết quả."""
    if seeds < 1 or repeats < 1:
        raise ValueError("seeds and repeats must be >= 1")
    
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    
    rows = run_trials(range(start_seed, start_seed + seeds), repeats)
    
    # Lưu raw data
    with (output / "raw.csv").open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    
    # Tổng hợp theo thuật toán
    summary = summarize(rows)
    with (output / "summary.csv").open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(summary[0]))
        writer.writeheader()
        writer.writerows(summary)
    
    # Tổng hợp theo input để so sánh công bằng
    by_input = []
    for seed in range(start_seed, start_seed + seeds):
        for algorithm in ("DFS", "HillClimbing"):
            samples = [row for row in rows 
                      if row["seed"] == seed and row["algorithm"] == algorithm]
            
            expanded = [s["expanded_nodes"] for s in samples if s["expanded_nodes"]]
            generated = [s["generated_nodes"] for s in samples if s["generated_nodes"]]
            
            by_input.append({
                "seed": seed,
                "rows": samples[0]["rows"],
                "cols": samples[0]["cols"],
                "mines": samples[0]["mines"],
                "algorithm": algorithm,
                "repeats": repeats,
                "median_planning_ms": statistics.median([s["planning_ms"] for s in samples]),
                "median_python_peak_kib": statistics.median([s["python_peak_kib"] for s in samples]),
                "median_expanded_nodes": statistics.median(expanded) if expanded else None,
                "median_generated_nodes": statistics.median(generated) if generated else None,
                "safe_cells_found": samples[0]["safe_cells_found"],
                "all_results_valid": all(s["valid_result"] for s in samples),
            })
    
    with (output / "by_input.csv").open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(by_input[0]))
        writer.writeheader()
        writer.writerows(by_input)
    
    # Metadata
    metadata = {
        "start_seed": start_seed,
        "seeds": seeds,
        "repeats": repeats,
        "backend_mode": "ai_reasoning",
        "notes": [
            "AI chỉ suy luận từ các con số hiển thị, không biết trước vị trí mìn.",
            "DFS dùng backtracking để tìm cấu hình mìn hợp lệ.",
            "Constraint propagation tìm ô an toàn/chắc chắn mìn mà không cần DFS.",
            "expanded_nodes: số trạng thái đã mở rộng trong quá trình tìm kiếm.",
            "generated_nodes: số trạng thái đã sinh (bao gồm cả trong queue).",
            "Hai thuật toán chỉ so sánh được khi cùng giải cùng một bài toán.",
        ],
    }
    (output / "metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2), 
        encoding="utf-8"
    )
    
    return summary


def main():
    parser = argparse.ArgumentParser(description="Benchmark Minesweeper AI solvers.")
    parser.add_argument("--seeds", type=int, default=10,
                        help="Số bàn cờ khác nhau (default: 10)")
    parser.add_argument("--repeats", type=int, default=3,
                        help="Số lần lặp cho mỗi bàn (default: 3)")
    parser.add_argument("--start-seed", type=int, default=0,
                        help="Seed bắt đầu (default: 0)")
    parser.add_argument("--output", type=Path, 
                        default=Path(__file__).resolve().parent / "benchmark_results",
                        help="Thư mục lưu kết quả")
    
    args = parser.parse_args()
    
    if args.seeds < 1 or args.repeats < 1:
        parser.error("--seeds and --repeats must be >= 1")
    
    for row in run_benchmark(args.output, args.seeds, args.repeats, args.start_seed):
        print(f"{row['algorithm']}: "
              f"{row['valid_results']}/{row['runs']} valid; "
              f"median {row['median_planning_ms']:.4f} ms; "
              f"expanded median {row.get('median_expanded_nodes', 'N/A')}; "
              f"Python peak {row['median_python_peak_kib']:.2f} KiB")
    
    print(f"\nKết quả lưu tại: {args.output.resolve()}")


if __name__ == "__main__":
    main()
