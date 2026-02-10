#!/usr/bin/env python
"""
Result Analysis Script for Persona-Review Similarity Experiments.

Usage:
    python analyze_results.py results/experiment_name_timestamp.json
    python analyze_results.py results/ --all
    python analyze_results.py results/exp.json --plot
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, List, Any

# Add project root to path
project_root = Path(__file__).parent.parent.parent.parent.parent
sys.path.insert(0, str(project_root))


def load_results(path: Path) -> Dict[str, Any]:
    """Load experiment results from JSON file."""
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def print_summary(data: Dict[str, Any]) -> None:
    """Print summary statistics."""
    print(f"\n{'='*60}")
    print(f"Experiment: {data['experiment_name']}")
    print(f"Timestamp: {data['timestamp']}")
    print(f"{'='*60}")

    results = data["results"]
    print(f"\nTotal combinations tested: {len(results)}")

    # Find best by each metric
    metrics = ["discrimination_score", "top_3_accuracy", "top_5_accuracy", "top_10_accuracy"]

    for metric in metrics:
        best = max(results, key=lambda x: x["metrics"].get(metric, 0))
        print(f"\nBest by {metric}:")
        print(f"  {best['prompt']} + {best['formatter']} + {best['embedder']}")
        print(f"  Value: {best['metrics'][metric]:.4f}")


def analyze_by_variable(data: Dict[str, Any]) -> None:
    """Analyze results grouped by each variable."""
    results = data["results"]

    # Group by prompt
    print("\n" + "=" * 60)
    print("ANALYSIS BY PROMPT")
    print("=" * 60)
    prompts = {}
    for r in results:
        p = r["prompt"]
        if p not in prompts:
            prompts[p] = []
        prompts[p].append(r["metrics"]["discrimination_score"])

    for prompt, scores in sorted(prompts.items()):
        avg = sum(scores) / len(scores)
        print(f"  {prompt:20} avg_disc={avg:.4f}")

    # Group by formatter
    print("\n" + "=" * 60)
    print("ANALYSIS BY FORMATTER")
    print("=" * 60)
    formatters = {}
    for r in results:
        f = r["formatter"]
        if f not in formatters:
            formatters[f] = []
        formatters[f].append(r["metrics"]["discrimination_score"])

    for formatter, scores in sorted(formatters.items()):
        avg = sum(scores) / len(scores)
        print(f"  {formatter:20} avg_disc={avg:.4f}")

    # Group by embedder
    print("\n" + "=" * 60)
    print("ANALYSIS BY EMBEDDER")
    print("=" * 60)
    embedders = {}
    for r in results:
        e = r["embedder"]
        if e not in embedders:
            embedders[e] = []
        embedders[e].append(r["metrics"]["discrimination_score"])

    for embedder, scores in sorted(embedders.items()):
        avg = sum(scores) / len(scores)
        print(f"  {embedder:25} avg_disc={avg:.4f}")


def create_heatmap(data: Dict[str, Any], output_path: str = None) -> None:
    """Create heatmap visualization."""
    try:
        import matplotlib.pyplot as plt
        import numpy as np
    except ImportError:
        print("matplotlib required for plotting. Install with: pip install matplotlib")
        return

    results = data["results"]

    # Get unique values
    prompts = sorted(set(r["prompt"] for r in results))
    formatters = sorted(set(r["formatter"] for r in results))
    embedders = sorted(set(r["embedder"] for r in results))

    # Create figure with subplots for each embedder
    fig, axes = plt.subplots(1, len(embedders), figsize=(6 * len(embedders), 5))
    if len(embedders) == 1:
        axes = [axes]

    for idx, embedder in enumerate(embedders):
        # Build matrix
        matrix = np.zeros((len(prompts), len(formatters)))
        for r in results:
            if r["embedder"] == embedder:
                i = prompts.index(r["prompt"])
                j = formatters.index(r["formatter"])
                matrix[i, j] = r["metrics"]["discrimination_score"]

        ax = axes[idx]
        im = ax.imshow(matrix, cmap="YlOrRd", aspect="auto")

        ax.set_xticks(range(len(formatters)))
        ax.set_yticks(range(len(prompts)))
        ax.set_xticklabels([f[:10] for f in formatters], rotation=45, ha="right")
        ax.set_yticklabels([p[:12] for p in prompts])
        ax.set_title(f"Embedder: {embedder[:15]}")

        # Add values
        for i in range(len(prompts)):
            for j in range(len(formatters)):
                ax.text(j, i, f"{matrix[i, j]:.2f}", ha="center", va="center", fontsize=8)

    plt.colorbar(im, ax=axes, label="Discrimination Score")
    plt.suptitle("Discrimination Score by Prompt × Formatter × Embedder")
    plt.tight_layout()

    if output_path:
        plt.savefig(output_path, dpi=150, bbox_inches="tight")
        print(f"Heatmap saved to: {output_path}")
    else:
        plt.show()


def export_csv(data: Dict[str, Any], output_path: str) -> None:
    """Export results to CSV."""
    results = data["results"]

    with open(output_path, "w", encoding="utf-8") as f:
        # Header
        f.write("prompt,formatter,embedder,avg_related_sim,avg_unrelated_sim,discrimination,top_3,top_5,top_10\n")

        for r in results:
            m = r["metrics"]
            f.write(
                f"{r['prompt']},{r['formatter']},{r['embedder']},"
                f"{m['avg_related_similarity']:.4f},{m['avg_unrelated_similarity']:.4f},"
                f"{m['discrimination_score']:.4f},"
                f"{m['top_3_accuracy']:.4f},{m['top_5_accuracy']:.4f},{m['top_10_accuracy']:.4f}\n"
            )

    print(f"CSV exported to: {output_path}")


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Analyze experiment results")
    parser.add_argument("path", help="Path to results JSON file or directory")
    parser.add_argument("--all", action="store_true", help="Analyze all files in directory")
    parser.add_argument("--plot", action="store_true", help="Generate heatmap visualization")
    parser.add_argument("--csv", type=str, help="Export to CSV file")
    parser.add_argument("--output", type=str, help="Output path for plot")

    args = parser.parse_args()
    path = Path(args.path)

    if args.all and path.is_dir():
        files = list(path.glob("*.json"))
        if not files:
            print(f"No JSON files found in {path}")
            return 1
        # Analyze most recent
        path = max(files, key=lambda f: f.stat().st_mtime)
        print(f"Analyzing most recent: {path.name}")

    if not path.exists():
        print(f"File not found: {path}")
        return 1

    data = load_results(path)

    print_summary(data)
    analyze_by_variable(data)

    if args.csv:
        export_csv(data, args.csv)

    if args.plot:
        output = args.output or str(path.with_suffix(".png"))
        create_heatmap(data, output)

    return 0


if __name__ == "__main__":
    sys.exit(main())
