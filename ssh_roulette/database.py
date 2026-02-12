"""Database models and operations for SSH Roulette."""

import aiosqlite
import asyncio
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any


class Database:
    """Database manager for SSH Roulette."""

    def __init__(self, db_path: str = "roulette.db"):
        """Initialize database manager.

        Args:
            db_path: Path to the SQLite database file
        """
        self.db_path = db_path
        self._lock = asyncio.Lock()

    async def initialize(self) -> None:
        """Initialize database schema."""
        async with aiosqlite.connect(self.db_path) as db:
            # Users table
            await db.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    ssh_key_fingerprint TEXT UNIQUE NOT NULL,
                    balance REAL NOT NULL DEFAULT 100.0,
                    last_bankruptcy_reset TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)

            # Bets table
            await db.execute("""
                CREATE TABLE IF NOT EXISTS bets (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    game_id INTEGER NOT NULL,
                    bet_type TEXT NOT NULL,
                    bet_value TEXT NOT NULL,
                    amount REAL NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (user_id) REFERENCES users (id),
                    FOREIGN KEY (game_id) REFERENCES games (id)
                )
            """)

            # Games table
            await db.execute("""
                CREATE TABLE IF NOT EXISTS games (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    winning_number INTEGER NOT NULL,
                    winning_color TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
            """)

            # Chat messages table
            await db.execute("""
                CREATE TABLE IF NOT EXISTS chat_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    message TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (user_id) REFERENCES users (id)
                )
            """)

            await db.commit()

    async def create_user(
        self, username: str, ssh_key_fingerprint: str, initial_balance: float = 100.0
    ) -> Optional[int]:
        """Create a new user.

        Args:
            username: The username
            ssh_key_fingerprint: SSH key fingerprint
            initial_balance: Starting balance (default: €100)

        Returns:
            User ID if successful, None otherwise
        """
        now = datetime.now(timezone.utc).isoformat()
        async with self._lock:
            try:
                async with aiosqlite.connect(self.db_path) as db:
                    cursor = await db.execute(
                        """
                        INSERT INTO users
                        (username, ssh_key_fingerprint, balance, created_at, updated_at)
                        VALUES (?, ?, ?, ?, ?)
                        """,
                        (username, ssh_key_fingerprint, initial_balance, now, now),
                    )
                    await db.commit()
                    return cursor.lastrowid
            except aiosqlite.IntegrityError:
                return None

    async def get_user_by_fingerprint(self, ssh_key_fingerprint: str) -> Optional[Dict[str, Any]]:
        """Get user by SSH key fingerprint.

        Args:
            ssh_key_fingerprint: SSH key fingerprint

        Returns:
            User data dict or None
        """
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM users WHERE ssh_key_fingerprint = ?", (ssh_key_fingerprint,)
            )
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def get_user_by_id(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Get user by ID.

        Args:
            user_id: User ID

        Returns:
            User data dict or None
        """
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT * FROM users WHERE id = ?", (user_id,))
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def update_user_balance(self, user_id: int, new_balance: float) -> bool:
        """Update user balance.

        Args:
            user_id: User ID
            new_balance: New balance amount

        Returns:
            True if successful, False otherwise
        """
        now = datetime.now(timezone.utc).isoformat()
        async with self._lock:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute(
                    "UPDATE users SET balance = ?, updated_at = ? WHERE id = ?",
                    (new_balance, now, user_id),
                )
                await db.commit()
                return True

    async def create_game(self, winning_number: int, winning_color: str) -> int:
        """Create a new game record.

        Args:
            winning_number: The winning number (0-36)
            winning_color: The winning color ('red', 'black', or 'green')

        Returns:
            Game ID
        """
        now = datetime.now(timezone.utc).isoformat()
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "INSERT INTO games (winning_number, winning_color, created_at) VALUES (?, ?, ?)",
                (winning_number, winning_color, now),
            )
            await db.commit()
            return cursor.lastrowid

    async def create_bet(
        self, user_id: int, game_id: int, bet_type: str, bet_value: str, amount: float
    ) -> int:
        """Create a new bet.

        Args:
            user_id: User ID
            game_id: Game ID
            bet_type: Type of bet (number, color, even/odd, etc.)
            bet_value: The value being bet on
            amount: Bet amount

        Returns:
            Bet ID
        """
        now = datetime.now(timezone.utc).isoformat()
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                """
                INSERT INTO bets (user_id, game_id, bet_type, bet_value, amount, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (user_id, game_id, bet_type, bet_value, amount, now),
            )
            await db.commit()
            return cursor.lastrowid

    async def get_game_bets(self, game_id: int) -> List[Dict[str, Any]]:
        """Get all bets for a game.

        Args:
            game_id: Game ID

        Returns:
            List of bet dicts
        """
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT * FROM bets WHERE game_id = ?", (game_id,))
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def add_chat_message(self, user_id: int, message: str) -> int:
        """Add a chat message.

        Args:
            user_id: User ID
            message: Chat message

        Returns:
            Message ID
        """
        now = datetime.now(timezone.utc).isoformat()
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "INSERT INTO chat_messages (user_id, message, created_at) VALUES (?, ?, ?)",
                (user_id, message, now),
            )
            await db.commit()
            return cursor.lastrowid

    async def get_recent_chat_messages(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get recent chat messages.

        Args:
            limit: Maximum number of messages to retrieve

        Returns:
            List of message dicts with user info
        """
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """
                SELECT c.*, u.username
                FROM chat_messages c
                JOIN users u ON c.user_id = u.id
                ORDER BY c.created_at DESC
                LIMIT ?
                """,
                (limit,),
            )
            rows = await cursor.fetchall()
            return [dict(row) for row in reversed(rows)]

    async def reset_bankrupt_users(self, reset_amount: float = 10.0) -> int:
        """Reset balance for bankrupt users (balance <= 0) who haven't been reset today.

        Args:
            reset_amount: Amount to give to bankrupt users

        Returns:
            Number of users reset
        """
        today = datetime.now(timezone.utc).date().isoformat()
        now = datetime.now(timezone.utc).isoformat()

        async with self._lock:
            async with aiosqlite.connect(self.db_path) as db:
                # Find bankrupt users who haven't been reset today
                cursor = await db.execute(
                    """
                    SELECT id FROM users
                    WHERE balance <= 0
                    AND (last_bankruptcy_reset IS NULL OR last_bankruptcy_reset < ?)
                    """,
                    (today,),
                )
                user_ids = [row[0] for row in await cursor.fetchall()]

                if user_ids:
                    # Update their balances
                    placeholders = ",".join("?" * len(user_ids))
                    await db.execute(
                        f"""
                        UPDATE users
                        SET balance = ?, last_bankruptcy_reset = ?, updated_at = ?
                        WHERE id IN ({placeholders})
                        """,
                        (reset_amount, today, now, *user_ids),
                    )
                    await db.commit()

                return len(user_ids)

    async def get_recent_games(self, limit: int = 5) -> List[Dict[str, Any]]:
        """Get recent game results.

        Args:
            limit: Maximum number of games to retrieve

        Returns:
            List of game dicts ordered most recent first
        """
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM games ORDER BY id DESC LIMIT ?",
                (limit,),
            )
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def get_all_users(self) -> List[Dict[str, Any]]:
        """Get all users.

        Returns:
            List of user dicts
        """
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT * FROM users ORDER BY username")
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]
