"""One-time (cached) build of the S&P 500 peer metric panel for relative ranking.
Run: python build_peers.py            # full S&P 500 (~10-15 min)
     python build_peers.py --force    # rebuild from scratch
Checkpoints every 25 names, so it's safe to interrupt & resume."""
import sys

from analyzer.peers import build_peer_panel

if __name__ == "__main__":
    force = "--force" in sys.argv
    build_peer_panel(force=force)
