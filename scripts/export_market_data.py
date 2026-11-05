#!/usr/bin/env python3
"""Export shared provider datasets for local QC research; does not submit cloud jobs."""
import argparse
import json


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--home", help="Shared runtime override (default: data_providers/runtime)")
    parser.add_argument("--backend", choices=["auto", "parquet", "duckdb"], default="auto")
    parser.add_argument("--release", help="Pin a verified Parquet release for reproducible research")
    parser.add_argument("--dataset", default="us_prices")
    parser.add_argument("--symbol", action="append", dest="symbols")
    parser.add_argument("--start")
    parser.add_argument("--end")
    parser.add_argument("--format", choices=["parquet", "csv"], default="parquet")
    parser.add_argument("--output", required=True, help="New export directory")
    args = parser.parse_args(argv)
    from data_providers import MarketData
    client = MarketData(args.home, backend=args.backend, release=args.release)
    manifest = client.export(args.dataset, args.output, format=args.format,
                             symbols=args.symbols, start=args.start, end=args.end)
    print(json.dumps({"provider_home": str(client.home), **manifest}, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
