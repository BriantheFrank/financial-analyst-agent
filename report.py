import argparse
from pathlib import Path

from viz.reporting import ReportGenerator, load_payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Sell-side style financial visualization report generator")
    parser.add_argument("--in", dest="input_json", required=True, help="Input JSON from SEC extractor")
    parser.add_argument("--outdir", required=True, help="Output directory")
    parser.add_argument("--format", nargs="+", choices=["png", "html"], default=["png"], help="Output format(s)")
    args = parser.parse_args()

    payload = load_payload(Path(args.input_json))
    generator = ReportGenerator(payload=payload, outdir=Path(args.outdir), formats=args.format)
    results = generator.generate()

    print("\nReport generation summary")
    print("=" * 80)
    for item in results:
        status = "GENERATED" if item.generated else "SKIPPED"
        files = ", ".join(item.files) if item.files else "-"
        print(f"{item.name:40s} | {status:9s} | {item.reason} | {files}")


if __name__ == "__main__":
    main()
