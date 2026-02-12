"""SSH server for Roulette game."""

import asyncio
import asyncssh
from asyncssh import SSHServerSession
from typing import Optional, Dict, Any, Set
import hashlib
import re
from datetime import datetime, timezone

from ssh_roulette.database import Database
from ssh_roulette.tui import RouletteTUI
from ssh_roulette.game import Bet, BetType, RouletteWheel


class GameState:
    """Shared game state across all sessions."""

    def __init__(self, database: Database):
        """Initialize game state.

        Args:
            database: Database instance
        """
        self.database = database
        self.sessions: Set["RouletteSession"] = set()
        self.current_game_id: Optional[int] = None
        self.last_spin_time: Optional[datetime] = None
        self.last_number: Optional[int] = None
        self.last_color: Optional[str] = None
        self.spin_interval = 300  # 5 minutes in seconds
        self.chat_messages: list = []
        self._lock = asyncio.Lock()
        self._spin_task: Optional[asyncio.Task] = None

    async def add_session(self, session: "RouletteSession") -> None:
        """Add a session to the game.

        Args:
            session: Session to add
        """
        async with self._lock:
            self.sessions.add(session)
            await self._ensure_spin_task()

    async def remove_session(self, session: "RouletteSession") -> None:
        """Remove a session from the game.

        Args:
            session: Session to remove
        """
        async with self._lock:
            self.sessions.discard(session)
            if not self.sessions and self._spin_task:
                self._spin_task.cancel()
                self._spin_task = None

    async def broadcast_message(
        self, message: str, exclude: Optional["RouletteSession"] = None
    ) -> None:
        """Broadcast a message to all sessions.

        Args:
            message: Message to broadcast
            exclude: Optional session to exclude from broadcast
        """
        async with self._lock:
            for session in self.sessions:
                if session != exclude:
                    try:
                        session.write(message + "\n")
                    except Exception:
                        pass

    async def add_chat_message(self, user_id: int, username: str, message: str) -> None:
        """Add a chat message and broadcast it.

        Args:
            user_id: User ID
            username: Username
            message: Chat message
        """
        await self.database.add_chat_message(user_id, message)
        async with self._lock:
            self.chat_messages.append(
                {
                    "username": username,
                    "message": message,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                }
            )
            # Keep only last 100 messages
            if len(self.chat_messages) > 100:
                self.chat_messages = self.chat_messages[-100:]

        await self.broadcast_message(f"[CHAT] {username}: {message}")

    async def _ensure_spin_task(self) -> None:
        """Ensure the auto-spin task is running."""
        if not self._spin_task or self._spin_task.done():
            self._spin_task = asyncio.create_task(self._auto_spin_loop())

    async def _auto_spin_loop(self) -> None:
        """Auto-spin the wheel every 5 minutes when users are connected."""
        while True:
            try:
                await asyncio.sleep(self.spin_interval)

                async with self._lock:
                    if self.sessions:
                        await self._spin_wheel()
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"Error in auto-spin loop: {e}")

    async def _spin_wheel(self) -> None:
        """Spin the wheel and process all bets."""
        # Spin the wheel
        number, color = RouletteWheel.spin()

        # Create game record
        game_id = await self.database.create_game(number, color)

        # Update state
        self.last_number = number
        self.last_color = color
        self.last_spin_time = datetime.now(timezone.utc)
        self.current_game_id = game_id

        # Broadcast result
        await self.broadcast_message(f"\n🎰 SPIN RESULT: {number} ({color.upper()}) 🎰\n")

        # Process any pending bets would go here
        # For now, just notify users
        for session in self.sessions:
            try:
                await session.refresh_display()
            except Exception:
                pass

    def get_seconds_until_spin(self) -> int:
        """Get seconds until next spin.

        Returns:
            Seconds until next spin
        """
        if not self.last_spin_time:
            return 0

        elapsed = (datetime.now(timezone.utc) - self.last_spin_time).total_seconds()
        remaining = max(0, self.spin_interval - elapsed)
        return int(remaining)


class RouletteSession(SSHServerSession):
    """SSH session for a Roulette player."""

    def __init__(self, game_state: GameState):
        """Initialize session.

        Args:
            game_state: Shared game state
        """
        self.game_state = game_state
        self.user_id: Optional[int] = None
        self.username: Optional[str] = None
        self.user_data: Optional[Dict[str, Any]] = None
        self.tui = RouletteTUI()
        self._chan: Optional[Any] = None
        self._should_exit = False

    def connection_made(self, chan: Any) -> None:
        """Called when connection is made.

        Args:
            chan: SSH channel
        """
        self._chan = chan

    def shell_requested(self) -> bool:
        """Handle shell request.

        Returns:
            True to accept shell request
        """
        return True

    def session_started(self) -> None:
        """Called when session starts."""
        asyncio.create_task(self._handle_session())

    async def _handle_session(self) -> None:
        """Handle the interactive session."""
        try:
            # Get SSH connection to retrieve key info
            conn = self._chan.get_connection()

            # Get SSH key fingerprint
            client_key = conn.get_key()
            if client_key:
                key_fingerprint = hashlib.sha256(client_key.get_ssh_public_key()).hexdigest()
            else:
                self.write(
                    "Error: No SSH key provided. Connection requires SSH key authentication.\n"
                )
                self._chan.exit(1)
                return

            # Look up or register user
            user = await self.game_state.database.get_user_by_fingerprint(key_fingerprint)

            if not user:
                # New user - register
                self.write(self.tui.clear())
                self.write(self.tui.render_registration())

                username = await self._read_line()
                username = username.strip()

                # Validate username
                if not re.match(r"^[a-zA-Z0-9_]{3,20}$", username):
                    self.write(
                        self.tui.render_error(
                            "Invalid username. Must be 3-20 alphanumeric characters."
                        )
                        + "\n"
                    )
                    self._chan.exit(1)
                    return

                # Create user
                user_id = await self.game_state.database.create_user(
                    username, key_fingerprint, 100.0
                )

                if not user_id:
                    self.write(self.tui.render_error("Username already taken.") + "\n")
                    self._chan.exit(1)
                    return

                user = await self.game_state.database.get_user_by_id(user_id)
                self.write(
                    self.tui.render_success(f"Welcome, {username}! You start with €100.00") + "\n"
                )
                await asyncio.sleep(2)

            self.user_id = user["id"]
            self.username = user["username"]
            self.user_data = user

            # Add session to game state
            await self.game_state.add_session(self)

            # Broadcast join
            await self.game_state.broadcast_message(
                f"*** {self.username} joined the game ***", exclude=self
            )

            # Load recent chat messages
            recent_messages = await self.game_state.database.get_recent_chat_messages(50)
            self.game_state.chat_messages = recent_messages

            # Main game loop
            await self._game_loop()

        except Exception as e:
            print(f"Session error: {e}")
        finally:
            await self.game_state.remove_session(self)
            if self.username:
                await self.game_state.broadcast_message(f"*** {self.username} left the game ***")

    async def _game_loop(self) -> None:
        """Main game loop."""
        while not self._should_exit:
            # Refresh user data
            self.user_data = await self.game_state.database.get_user_by_id(self.user_id)

            # Display game screen
            await self.refresh_display()

            # Read command
            self.write("> ")
            command = await self._read_line()

            if not command:
                continue

            command = command.strip()

            # Check if it's a slash command
            if command.startswith("/"):
                await self._handle_slash_command(command[1:])
            else:
                # Regular message - send as chat
                if command:
                    await self.game_state.add_chat_message(self.user_id, self.username, command)

    async def _handle_slash_command(self, command: str) -> None:
        """Handle slash commands.

        Args:
            command: Command without the leading slash
        """
        parts = command.strip().split()
        if not parts:
            return

        cmd = parts[0].lower()

        if cmd == "quit" or cmd == "exit":
            self.write("Goodbye!\n")
            # Need to signal to exit the loop - set a flag
            self._should_exit = True
            return
        elif cmd == "help":
            self.write(self.tui.render_bet_options())
        elif cmd == "users":
            await self._show_users()
        elif cmd == "bet" and len(parts) >= 3:
            # /bet <type> <value> <amount>
            # Examples:
            #   /bet number 17 10
            #   /bet split 5,6 20
            #   /bet corner 1,2,4,5 15
            #   /bet color red 25
            #   /bet even 10
            #   /bet odd 10
            #   /bet high 10
            #   /bet low 10
            await self._handle_bet_command(parts[1:])
        else:
            self.write(self.tui.render_error("Invalid command. Type '/help' for options.") + "\n")

    async def _handle_bet_command(self, args: list) -> None:
        """Handle bet command.

        Args:
            args: Command arguments (type, value, amount)
        """
        if len(args) < 2:
            self.write(self.tui.render_error("Usage: /bet <type> <value> <amount>") + "\n")
            return

        bet_type_str = args[0].lower()

        # Map command types to BetType
        if bet_type_str == "number":
            if len(args) != 3:
                self.write(self.tui.render_error("Usage: /bet number <0-36> <amount>") + "\n")
                return
            await self._place_bet(BetType.NUMBER, args[1], args[2])

        elif bet_type_str == "split":
            if len(args) != 3:
                self.write(self.tui.render_error("Usage: /bet split <n1,n2> <amount>") + "\n")
                return
            await self._place_bet(BetType.SPLIT, args[1], args[2])

        elif bet_type_str == "corner":
            if len(args) != 3:
                self.write(
                    self.tui.render_error("Usage: /bet corner <n1,n2,n3,n4> <amount>") + "\n"
                )
                return
            await self._place_bet(BetType.CORNER, args[1], args[2])

        elif bet_type_str == "color":
            if len(args) != 3:
                self.write(self.tui.render_error("Usage: /bet color <red/black> <amount>") + "\n")
                return
            await self._place_bet(BetType.COLOR, args[1], args[2])

        elif bet_type_str in ["even", "odd"]:
            if len(args) != 2:
                self.write(self.tui.render_error("Usage: /bet even/odd <amount>") + "\n")
                return
            await self._place_bet(BetType.EVEN_ODD, bet_type_str, args[1])

        elif bet_type_str in ["high", "low"]:
            if len(args) != 2:
                self.write(self.tui.render_error("Usage: /bet high/low <amount>") + "\n")
                return
            await self._place_bet(BetType.HIGH_LOW, bet_type_str, args[1])

        else:
            self.write(
                self.tui.render_error(
                    f"Unknown bet type: {bet_type_str}. Type '/help' for options."
                )
                + "\n"
            )

    async def _place_bet(self, bet_type: BetType, value: str, amount_str: str) -> None:
        """Place a bet.

        Args:
            bet_type: Type of bet
            value: Bet value
            amount_str: Bet amount as string
        """
        try:
            amount = float(amount_str)
        except ValueError:
            self.write(self.tui.render_error("Invalid amount") + "\n")
            return

        # Validate bet
        error = Bet.validate_bet(bet_type.value, value, amount, self.user_data["balance"])

        if error:
            self.write(self.tui.render_error(error) + "\n")
            return

        # For now, just acknowledge the bet
        # In a full implementation, bets would be stored and processed on next spin
        self.write(
            self.tui.render_success(f"Bet placed: {bet_type.value} on {value} for €{amount:.2f}")
            + "\n"
        )

        # Update balance
        new_balance = self.user_data["balance"] - amount
        await self.game_state.database.update_user_balance(self.user_id, new_balance)

    async def _show_users(self) -> None:
        """Show connected users."""
        users = []
        for session in self.game_state.sessions:
            if session.username:
                users.append(session.username)

        self.write("\nConnected users:\n")
        for username in sorted(users):
            self.write(f"  • {username}\n")
        self.write("\n")

    async def refresh_display(self) -> None:
        """Refresh the game display."""
        self.write(self.tui.clear())

        screen = self.tui.render_full_screen(
            username=self.username,
            balance=self.user_data["balance"],
            last_number=self.game_state.last_number,
            last_color=self.game_state.last_color,
            chat_messages=self.game_state.chat_messages,
            seconds_until_spin=self.game_state.get_seconds_until_spin(),
            num_users=len(self.game_state.sessions),
        )

        self.write(screen + "\n")

    async def _read_line(self) -> str:
        """Read a line of input.

        Returns:
            Input line
        """
        try:
            line = await asyncio.wait_for(self._chan.stdin.readline(), timeout=300)
            return line.strip()
        except asyncio.TimeoutError:
            return ""

    def write(self, data: str) -> None:
        """Write data to the channel.

        Args:
            data: Data to write
        """
        if self._chan and not self._chan.is_closing():
            self._chan.write(data)


class RouletteServer(asyncssh.SSHServer):
    """SSH server for Roulette."""

    def __init__(self, game_state: GameState):
        """Initialize server.

        Args:
            game_state: Shared game state
        """
        self.game_state = game_state

    def begin_auth(self, username: str) -> bool:
        """Begin authentication.

        Args:
            username: Username attempting to connect

        Returns:
            True to allow authentication
        """
        # We use SSH key authentication only
        return True

    def public_key_auth_supported(self) -> bool:
        """Check if public key auth is supported.

        Returns:
            True
        """
        return True

    def validate_public_key(self, username: str, key: Any) -> bool:
        """Validate public key.

        Args:
            username: Username
            key: SSH public key

        Returns:
            True to accept any key (we'll handle registration in the session)
        """
        # Accept all keys - we handle user registration in the session
        return True

    def session_requested(self) -> RouletteSession:
        """Create a new session.

        Returns:
            New RouletteSession instance
        """
        return RouletteSession(self.game_state)
