"""Main server entry point for SSH Roulette."""

import asyncio
import asyncssh
import argparse
import sys
from pathlib import Path

from ssh_roulette.database import Database
from ssh_roulette.ssh_server import GameState, RouletteServer


async def start_server(
    host: str = "0.0.0.0",
    port: int = 2222,
    db_path: str = "roulette.db",
    host_key: str = "host_key",
) -> None:
    """Start the SSH Roulette server.

    Args:
        host: Host to bind to
        port: Port to bind to
        db_path: Path to database file
        host_key: Path to host key file
    """
    # Initialize database
    db = Database(db_path)
    await db.initialize()

    # Reset bankrupt users if needed
    reset_count = await db.reset_bankrupt_users()
    if reset_count > 0:
        print(f"Reset {reset_count} bankrupt users with €10.00")

    # Create game state
    game_state = GameState(db)

    # Generate host key if it doesn't exist
    host_key_path = Path(host_key)
    if not host_key_path.exists():
        print(f"Generating host key at {host_key}...")
        key = asyncssh.generate_private_key("ssh-rsa")
        host_key_path.write_bytes(key.export_private_key())

    # Start SSH server
    print(f"Starting SSH Roulette server on {host}:{port}...")
    print(f"Database: {db_path}")
    print(f"Host key: {host_key}")
    print("\nConnect with: ssh -p {port} localhost")

    await asyncssh.create_server(
        lambda: RouletteServer(game_state),
        host,
        port,
        server_host_keys=[host_key],
    )

    # Keep server running
    await asyncio.Event().wait()


def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="SSH Roulette Server")
    parser.add_argument(
        "--host",
        default="0.0.0.0",
        help="Host to bind to (default: 0.0.0.0)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=2222,
        help="Port to bind to (default: 2222)",
    )
    parser.add_argument(
        "--db",
        default="roulette.db",
        help="Database file path (default: roulette.db)",
    )
    parser.add_argument(
        "--host-key",
        default="host_key",
        help="Host key file path (default: host_key)",
    )

    args = parser.parse_args()

    try:
        asyncio.run(
            start_server(
                host=args.host,
                port=args.port,
                db_path=args.db,
                host_key=args.host_key,
            )
        )
    except KeyboardInterrupt:
        print("\nServer stopped.")
        sys.exit(0)


if __name__ == "__main__":
    main()
