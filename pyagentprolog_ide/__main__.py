"""python -m pyagentprolog_ide"""
import argparse


def main() -> None:
    from .app import launch

    p = argparse.ArgumentParser(description="PyAgentProlog IDE")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=7860)
    p.add_argument("--share", action="store_true")
    args = p.parse_args()

    launch(host=args.host, port=args.port, share=args.share)


if __name__ == "__main__":
    main()