import argparse
import logging

from aptfinder.config import get_settings
from aptfinder.db.models import utcnow
from aptfinder.db.session import session_scope
from aptfinder.pipeline import RunContext, apply_hard_filters, collect_listings, finish_run, make_client, resolve_cities, start_run


def run(args: argparse.Namespace) -> None:
    settings = get_settings()
    client = make_client(settings)
    with session_scope() as session:
        run_row = start_run(session)
        ctx = RunContext(run_row, settings, client)
        try:
            if not args.skip_collection:
                collect_listings(session, ctx, resolve_cities(args.cities), args.sources)
            ctx.stats.update({f"status.{k}": v for k, v in apply_hard_filters(session, settings, utcnow()).items()})
            ctx.stats["network_requests"] = client.network_requests
            finish_run(session, ctx)
        except Exception:
            ctx.stats["network_requests"] = client.network_requests
            finish_run(session, ctx, failed=True)
            raise
        finally:
            client.close()
        print(f"Run {run_row.id}: {run_row.status}")
        for key, value in sorted(ctx.stats.items()):
            print(f"  {key}: {value}")
        for limitation in ctx.limitations:
            print(f"  limitation [{limitation['source_id']}]: {limitation['message']}")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser(prog="aptfinder")
    sub = parser.add_subparsers(dest="command", required=True)
    run_parser = sub.add_parser("run", help="Collect, filter, evaluate, and audit apartments")
    run_parser.add_argument("--cities", type=lambda s: s.split(","), default=None, help="Comma-separated subset of search cities")
    run_parser.add_argument("--sources", type=lambda s: s.split(","), default=["apartment_list", "redfin"])
    run_parser.add_argument("--skip-collection", action="store_true", help="Re-run filters and evaluation on stored evidence only")
    run_parser.set_defaults(func=run)
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
