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
        self.round_history: list = []  # List of recent round results
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
        # Set the initial reference time so the countdown starts immediately
        if not self.last_spin_time:
            self.last_spin_time = datetime.now(timezone.utc)
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

        # Update round history
        self.round_history.insert(0, {"id": game_id, "winning_number": number, "winning_color": color})
        self.round_history = self.round_history[:10]  # Keep last 10

        # Broadcast result
        await self.broadcast_message(f"\n🎰 SPIN RESULT: {number} ({color.upper()}) 🎰\n")

        # Process any pending bets would go here
        # For now, just notify users
        for session in self.sessions:
            try:
                session.active_bets.clear()  # Clear bets after spin
                await session.refresh_display()
            except Exception:
                pass

    def get_seconds_until_spin(self) -> int:
        """Get seconds until next spin.

        Returns:
            Seconds until next spin
        """
        if not self.last_spin_time:
            return self.spin_interval

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
        self.active_bets: list = []  # Bets placed for the current round
        # Buffer for incoming data
        self._input_buffer = ""
        self._input_queue: asyncio.Queue = asyncio.Queue()

    def connection_made(self, chan: Any) -> None:
        """Called when connection is made.

        Args:
            chan: SSH channel
        """
        self._chan = chan

    def data_received(self, data: str, datatype: Optional[int]) -> None:
        """Handle incoming data from the client.

        Args:
            data: Data received from client
            datatype: Extended data type
        """
        # Buffer the incoming data
        self._input_buffer += data

        # Process complete lines (terminated by newline)
        while "\n" in self._input_buffer:
            line, self._input_buffer = self._input_buffer.split("\n", 1)
            # Put the line in the queue for reading
            try:
                self._input_queue.put_nowait(line.rstrip("\r"))
            except asyncio.QueueFull:
                # Queue is full, skip this line
                pass

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

            # Get SSH key fingerprint from extra_info (stored during authentication)
            client_key = conn.get_extra_info("client_public_key")
            if client_key:
                key_fingerprint = hashlib.sha256(client_key.encode_ssh_public()).hexdigest()
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

            # Load round history if not already loaded
            if not self.game_state.round_history:
                self.game_state.round_history = await self.game_state.database.get_recent_games(10)

            # Main game loop
            await self._game_loop()

        except Exception as e:
            print(f"Session error: {e}")
        finally:
            await self.game_state.remove_session(self)
            if self.username:
                await self.game_state.broadcast_message(f"*** {self.username} left the game ***")

    async def _game_loop(self) -> None:
        """Main game loop with periodic display refresh."""
        refresh_task: Optional[asyncio.Task] = None

        async def _periodic_refresh() -> None:
            """Refresh the display every second to update the countdown timer."""
            try:
                while not self._should_exit:
                    await asyncio.sleep(1)
                    if not self._should_exit:
                        self.user_data = await self.game_state.database.get_user_by_id(
                            self.user_id
                        )
                        await self.refresh_display()
                        self.write("> ")
            except asyncio.CancelledError:
                pass

        try:
            # Initial display
            await self.refresh_display()
            self.write("> ")
            refresh_task = asyncio.create_task(_periodic_refresh())

            while not self._should_exit:
                # Read command (blocks until input arrives)
                command = await self._read_line()

                if not command:
                    continue

                command = command.strip()
                if not command:
                    continue

                # Pause periodic refresh while processing command
                if refresh_task and not refresh_task.done():
                    refresh_task.cancel()
                    try:
                        await refresh_task
                    except asyncio.CancelledError:
                        pass

                # Refresh user data
                self.user_data = await self.game_state.database.get_user_by_id(self.user_id)

                # Check if it's a slash command
                if command.startswith("/"):
                    await self._handle_slash_command(command[1:])
                else:
                    # Regular message - send as chat
                    await self.game_state.add_chat_message(
                        self.user_id, self.username, command
                    )

                if not self._should_exit:
                    # Refresh display after command and restart periodic refresh
                    self.user_data = await self.game_state.database.get_user_by_id(
                        self.user_id
                    )
                    await self.refresh_display()
                    self.write("> ")
                    refresh_task = asyncio.create_task(_periodic_refresh())
        finally:
            if refresh_task and not refresh_task.done():
                refresh_task.cancel()
                try:
                    await refresh_task
                except asyncio.CancelledError:
                    pass

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
        elif cmd == "bet" and len(parts) >= 2:
            # Simplified syntax (amount first, then position(s)):
            #   /bet 10 17           - Bet €10 on number 17
            #   /bet 20 5,6          - Bet €20 on split 5,6
            #   /bet 15 1,2,4,5      - Bet €15 on corner
            #   /bet 25 red          - Bet €25 on red
            #   /bet 15 even         - Bet €15 on even
            #   /bet 10 high         - Bet €10 on high
            #   /bet 30 1st12        - Bet €30 on first dozen
            #   /bet 25 col1         - Bet €25 on column 1
            #   /bet 5 17 23 8       - Bet €5 on each of 17, 23, and 8
            # Legacy syntax (still supported):
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
            args: Command arguments with simplified syntax: /bet <amount> <position(s)>
                  or legacy syntax: /bet <type> <value> <amount>
        """
        if len(args) < 2:
            self.write(self.tui.render_error("Usage: /bet <amount> <position(s)>") + "\n")
            return

        # Check if first argument is an amount (simplified syntax)
        # This is a quick check to determine which parsing path to take
        # Actual validation with error messages happens in _handle_simplified_bet
        try:
            float(args[0])  # Check if it parses as a number
            # Simplified syntax detected - pass original string to preserve format
            await self._handle_simplified_bet(args[0], args[1:])
            return
        except ValueError:
            pass  # Not an amount, try legacy syntax

        # Legacy syntax: /bet <type> <value> <amount>
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

    async def _handle_simplified_bet(self, amount_str: str, positions: list) -> None:
        """Handle simplified bet syntax.

        Args:
            amount_str: Bet amount as string
            positions: Position(s) to bet on
        """
        if not positions:
            self.write(self.tui.render_error("Please specify position(s) to bet on") + "\n")
            return

        # Validate amount
        try:
            float(amount_str)  # Validate it's a number
        except ValueError:
            self.write(self.tui.render_error("Invalid amount") + "\n")
            return

        # Handle multiple positions (bet same amount on each)
        if len(positions) > 1:
            # Check if all positions are numbers
            try:
                numbers = [int(p) for p in positions]
                if all(0 <= n <= 36 for n in numbers):
                    # Multiple straight-up bets
                    for num_str in positions:
                        await self._place_bet(BetType.NUMBER, num_str, amount_str)
                    return
            except ValueError:
                pass  # Not all numbers, show error

            self.write(
                self.tui.render_error(
                    "Multiple positions must be numbers 0-36 for straight-up bets"
                )
                + "\n"
            )
            return

        # Single position
        position = positions[0].lower()

        # Try to parse as a single number
        try:
            number = int(position)
            if 0 <= number <= 36:
                await self._place_bet(BetType.NUMBER, position, amount_str)
                return
        except ValueError:
            pass

        # Check for comma-separated numbers (split or corner)
        if "," in position:
            numbers = position.split(",")
            if len(numbers) == 2:
                # Split bet
                await self._place_bet(BetType.SPLIT, position, amount_str)
                return
            elif len(numbers) == 4:
                # Corner bet
                await self._place_bet(BetType.CORNER, position, amount_str)
                return
            else:
                self.write(
                    self.tui.render_error(
                        "Comma-separated bets: 2 numbers (split) or 4 numbers (corner)"
                    )
                    + "\n"
                )
                return

        # Even chances
        if position in ["red", "black"]:
            await self._place_bet(BetType.COLOR, position, amount_str)
            return

        if position in ["even", "odd"]:
            await self._place_bet(BetType.EVEN_ODD, position, amount_str)
            return

        if position in ["high", "low"]:
            await self._place_bet(BetType.HIGH_LOW, position, amount_str)
            return

        # Dozens
        if position in ["1st12", "2nd12", "3rd12", "1-12", "13-24", "25-36"]:
            # Map to dozen value
            dozen_map = {
                "1st12": "1",
                "1-12": "1",
                "2nd12": "2",
                "13-24": "2",
                "3rd12": "3",
                "25-36": "3",
            }
            await self._place_bet(BetType.DOZEN, dozen_map[position], amount_str)
            return

        # Columns
        if position in ["col1", "col2", "col3", "column1", "column2", "column3"]:
            # Map to column value
            column_map = {
                "col1": "1",
                "column1": "1",
                "col2": "2",
                "column2": "2",
                "col3": "3",
                "column3": "3",
            }
            await self._place_bet(BetType.COLUMN, column_map[position], amount_str)
            return

        # Unknown position
        self.write(
            self.tui.render_error(f"Unknown position: {position}. Type '/help' for options.") + "\n"
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
            async with self.game_state._lock:
                self.game_state.chat_messages.append({
                    "username": "*",
                    "message": "Bet rejected: Invalid amount",
                    "created_at": datetime.now(timezone.utc).isoformat(),
                })
            return

        # Validate bet
        error = Bet.validate_bet(bet_type.value, value, amount, self.user_data["balance"])

        if error:
            # Add error feedback as a system chat message
            async with self.game_state._lock:
                self.game_state.chat_messages.append({
                    "username": "*",
                    "message": f"Bet rejected: {error}",
                    "created_at": datetime.now(timezone.utc).isoformat(),
                })
            return

        # Track active bet for display
        self.active_bets.append({
            "bet_type": bet_type.value,
            "value": value,
            "amount": amount,
        })

        # Update balance
        new_balance = self.user_data["balance"] - amount
        await self.game_state.database.update_user_balance(self.user_id, new_balance)

        # Add success feedback as a system chat message
        async with self.game_state._lock:
            self.game_state.chat_messages.append({
                "username": "*",
                "message": f"{self.username} bet €{amount:.0f} on {bet_type.value} {value}",
                "created_at": datetime.now(timezone.utc).isoformat(),
            })

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
            round_history=self.game_state.round_history,
            active_bets=self.active_bets,
        )

        self.write(screen + "\n")

    async def _read_line(self) -> str:
        """Read a line of input.

        Returns:
            Input line
        """
        try:
            line = await asyncio.wait_for(self._input_queue.get(), timeout=300)
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
        self._conn = None

    def connection_made(self, conn: asyncssh.SSHServerConnection) -> None:
        """Called when connection is established.

        Args:
            conn: SSH server connection
        """
        self._conn = conn

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
        # Store the client's public key for later use in the session
        if self._conn:
            self._conn.set_extra_info(client_public_key=key)
        # Accept all keys - we handle user registration in the session
        return True

    def session_requested(self) -> RouletteSession:
        """Create a new session.

        Returns:
            New RouletteSession instance
        """
        return RouletteSession(self.game_state)
