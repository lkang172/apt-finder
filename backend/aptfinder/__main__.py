import argparse
import logging

import uvicorn

from aptfinder.config import get_settings
from aptfinder.db.session import session_scope
from aptfinder.pipeline import DEFAULT_SOURCES, execute_run, start_run


def run(args: argparse.Namespace) -> None:
    with session_scope() as session:
        run_id = start_run(session).id
    ctx = execute_run(run_id, get_settings(), args.cities, args.sources, args.skip_collection)
    print(f"Run {run_id}: {ctx.run.status}")
    for key, value in sorted(ctx.stats.items()):
        print(f"  {key}: {value}")
    for limitation in ctx.limitations:
        print(f"  limitation [{limitation['source_id']}]: {limitation['message']}")


def serve(args: argparse.Namespace) -> None:
    uvicorn.run("aptfinder.api.app:app", host=args.host, port=args.port, reload=args.reload)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    parser = argparse.ArgumentParser(prog="aptfinder")
    sub = parser.add_subparsers(dest="command", required=True)
    run_parser = sub.add_parser("run", help="Collect, filter, evaluate, and audit apartments")
    run_parser.add_argument("--cities", type=lambda v: v.split(","), default=None, help="Comma-separated subset of search cities")
    run_parser.add_argument("--sources", type=lambda v: v.split(","), default=list(DEFAULT_SOURCES), help="Comma-separated sources: apartment_list, redfin")
    run_parser.add_argument("--skip-collection", action="store_true", help="Re-run filters and evaluation on stored evidence only")
    run_parser.set_defaults(func=run)
    serve_parser = sub.add_parser("serve", help="Start the API server")
    serve_parser.add_argument("--host", default="127.0.0.1")
    serve_parser.add_argument("--port", type=int, default=8000)
    serve_parser.add_argument("--reload", action="store_true")
    serve_parser.set_defaults(func=serve)
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
