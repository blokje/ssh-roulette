"""Terminal User Interface for SSH Roulette."""

from blessed import Terminal
from typing import List, Dict, Any, Optional


# Layout constants
FULL_WIDTH = 80
FULL_INNER = FULL_WIDTH - 2  # 78, inside │...│

# Bottom section: chat (left) + last rounds (right)
CHAT_OUTER = 52
CHAT_INNER = CHAT_OUTER - 2  # 50

ROUNDS_OUTER = FULL_WIDTH - CHAT_OUTER - 1  # 27 (1 char gap)
ROUNDS_INNER = ROUNDS_OUTER - 2  # 25

# Board section: board (left) + active bets (right)
BOARD_OUTER = 54
BOARD_INNER = BOARD_OUTER - 2  # 52

BETS_OUTER = FULL_WIDTH - BOARD_OUTER - 1  # 25
BETS_INNER = BETS_OUTER - 2  # 23

CHAT_LINES = 6


class RouletteTUI:
    """Terminal User Interface for Roulette game."""

    def __init__(self):
        """Initialize the TUI."""
        self.term = Terminal()
        self.width = FULL_WIDTH
        self.height = 24

    def clear(self) -> str:
        """Clear the screen.

        Returns:
            ANSI escape codes to clear screen
        """
        return self.term.clear()

    # ── Box drawing helpers ──────────────────────────────────────────────

    def _box_top(self, inner_w: int) -> str:
        return "┌" + "─" * inner_w + "┐"

    def _box_bottom(self, inner_w: int) -> str:
        return "└" + "─" * inner_w + "┘"

    def _box_row(self, text: str, plain_len: int, inner_w: int) -> str:
        """Build a box row: │<text padded to inner_w>│.

        Args:
            text: Text (may contain ANSI codes)
            plain_len: Length of visible characters in text
            inner_w: Inner width of the box
        """
        pad = inner_w - plain_len
        if pad < 0:
            pad = 0
        return "│" + text + " " * pad + "│"

    # ── Status bar ───────────────────────────────────────────────────────

    def render_status_bar(self, seconds_until_spin: int, balance: float) -> str:
        """Render the top status bar.

        Args:
            seconds_until_spin: Seconds until next spin
            balance: Current balance

        Returns:
            Rendered status bar (3 lines)
        """
        mins = seconds_until_spin // 60
        secs = seconds_until_spin % 60

        if mins > 0:
            time_str = f"in {mins} minute{'s' if mins != 1 else ''}"
        else:
            time_str = f"in {secs} seconds"

        left = f" Next round: {time_str}"
        right = f"Balance: {int(balance)} "
        gap = FULL_INNER - len(left) - len(right)
        if gap < 1:
            gap = 1
        plain_row = left + " " * gap + right

        lines = []
        lines.append(self._box_top(FULL_INNER))
        lines.append(self._box_row(plain_row, len(plain_row), FULL_INNER))
        lines.append(self._box_bottom(FULL_INNER))
        return "\n".join(lines)

    # ── Roulette board ───────────────────────────────────────────────────

    def render_roulette_board(
        self, last_number: Optional[int] = None, last_color: Optional[str] = None
    ) -> List[str]:
        """Render the roulette board with 0 on the left side.

        Layout (inside the box)::

            │   │  3   6   9  12  15  18  21  24  27  30  33  36  │
            │ 0 │  2   5   8  11  14  17  20  23  26  29  32  35  │
            │   │  1   4   7  10  13  16  19  22  25  28  31  34  │

        Args:
            last_number: Last winning number
            last_color: Last winning color

        Returns:
            List of rendered lines
        """
        from ssh_roulette.game import RouletteWheel

        lines: List[str] = []
        lines.append(self._box_top(BOARD_INNER))

        # Blank line above the grid
        lines.append(self._box_row("", 0, BOARD_INNER))

        # 3 number rows with 0 on the left of the middle row
        for row_start in [3, 2, 1]:
            # Zero column: show "0" only in the middle row (row_start==2)
            if row_start == 2:
                zero_plain = " 0 │"
                zero_styled = (
                    f" {self.term.green}{self.term.bold}0{self.term.normal} │"
                )
            else:
                zero_plain = "   │"
                zero_styled = "   │"

            plain_parts = []
            styled_parts = []
            for col in range(12):
                num = row_start + (col * 3)
                color = RouletteWheel.get_color(num)
                num_str = f"{num:>2}"
                plain_parts.append(f"{num_str}  ")
                if color == "red":
                    styled_parts.append(
                        f"{self.term.red}{num_str}{self.term.normal}  "
                    )
                elif color == "black":
                    styled_parts.append(
                        f"{self.term.white}{num_str}{self.term.normal}  "
                    )
                else:
                    styled_parts.append(
                        f"{self.term.green}{num_str}{self.term.normal}  "
                    )

            nums_plain = " ".join([]) if not plain_parts else "".join(plain_parts)
            nums_styled = "".join(styled_parts)
            full_plain = zero_plain + nums_plain
            full_styled = zero_styled + nums_styled
            lines.append(self._box_row(full_styled, len(full_plain), BOARD_INNER))

        # Blank line
        lines.append(self._box_row("", 0, BOARD_INNER))

        # Last result line
        if last_number is not None and last_color is not None:
            result_plain = f" Last: {last_number} ({last_color})"
            color_fn = {"red": self.term.red, "black": self.term.white}.get(
                last_color, self.term.green
            )
            result_styled = (
                f" Last: {color_fn}{self.term.bold}{last_number}{self.term.normal}"
                f" ({last_color})"
            )
        else:
            result_plain = " Waiting for first spin..."
            result_styled = " Waiting for first spin..."
        lines.append(self._box_row(result_styled, len(result_plain), BOARD_INNER))

        # Blank line
        lines.append(self._box_row("", 0, BOARD_INNER))
        lines.append(self._box_bottom(BOARD_INNER))
        return lines

    # ── Active bets panel ────────────────────────────────────────────────

    def render_active_bets_panel(
        self, active_bets: List[Dict[str, Any]], total_lines: int = 8
    ) -> List[str]:
        """Render the active bets box as a list of lines.

        Args:
            active_bets: List of bet dicts with 'bet_type', 'value', 'amount'.
            total_lines: Total content lines (to match board height).

        Returns:
            List of rendered lines
        """
        lines: List[str] = []
        lines.append(self._box_top(BETS_INNER))

        header = " Active bets:"
        lines.append(self._box_row(header, len(header), BETS_INNER))

        content_used = 1
        if active_bets:
            for bet in active_bets[: total_lines - 2]:
                btype = bet.get("bet_type", "?")
                value = bet.get("value", "?")
                amount = bet.get("amount", 0)
                text = f"  {btype} {value} €{amount:.0f}"
                if len(text) > BETS_INNER:
                    text = text[: BETS_INNER - 1] + "…"
                lines.append(self._box_row(text, len(text), BETS_INNER))
                content_used += 1
        else:
            no_bets = "  (none)"
            lines.append(self._box_row(no_bets, len(no_bets), BETS_INNER))
            content_used += 1

        # Fill remaining
        for _ in range(total_lines - content_used):
            lines.append(self._box_row("", 0, BETS_INNER))

        lines.append(self._box_bottom(BETS_INNER))
        return lines

    # ── Chat panel ───────────────────────────────────────────────────────

    def render_chat_panel(
        self, messages: List[Dict[str, Any]], max_lines: int = CHAT_LINES,
    ) -> List[str]:
        """Render the chat message box as a list of lines.

        Args:
            messages: List of message dicts with 'username' and 'message'
            max_lines: Number of message lines visible

        Returns:
            List of rendered lines (top border, content, bottom border)
        """
        lines = []
        lines.append(self._box_top(CHAT_INNER))

        recent = messages[-max_lines:] if messages else []
        for msg in recent:
            username = msg.get("username", "System")
            message = msg.get("message", "")

            # Format: <user> message  or  * system message
            if username == "System" or username == "*":
                plain = f" * {message}"
                styled = f" {self.term.yellow}*{self.term.normal} {message}"
            else:
                plain = f" <{username}> {message}"
                styled = (
                    f" {self.term.cyan}<{username}>{self.term.normal} {message}"
                )

            # Truncate if needed
            if len(plain) > CHAT_INNER:
                excess = len(plain) - CHAT_INNER + 3
                message = message[: len(message) - excess] + "..."
                if username == "System" or username == "*":
                    plain = f" * {message}"
                    styled = f" {self.term.yellow}*{self.term.normal} {message}"
                else:
                    plain = f" <{username}> {message}"
                    styled = (
                        f" {self.term.cyan}<{username}>{self.term.normal} {message}"
                    )

            lines.append(self._box_row(styled, len(plain), CHAT_INNER))

        # Fill empty lines
        for _ in range(max_lines - len(recent)):
            lines.append(self._box_row("", 0, CHAT_INNER))

        lines.append(self._box_bottom(CHAT_INNER))
        return lines

    # ── Last rounds panel ────────────────────────────────────────────────

    def render_last_rounds_panel(
        self, round_history: List[Dict[str, Any]], total_lines: int = 8
    ) -> List[str]:
        """Render the last rounds box as a list of lines.

        Args:
            round_history: Recent rounds, most-recent first.
                Each dict has 'winning_number' and optionally 'winning_color'.
            total_lines: Total content lines (to match chat height)

        Returns:
            List of rendered lines
        """
        lines = []
        lines.append(self._box_top(ROUNDS_INNER))

        # Header
        header = " Last rounds:"
        lines.append(self._box_row(header, len(header), ROUNDS_INNER))

        content_lines_used = 1
        for i, rnd in enumerate(round_history[: total_lines - 2]):
            num = rnd.get("winning_number", "?")
            text = f"   #{i + 1} - {num}"
            lines.append(self._box_row(text, len(text), ROUNDS_INNER))
            content_lines_used += 1

        # Fill remaining
        for _ in range(total_lines - content_lines_used):
            lines.append(self._box_row("", 0, ROUNDS_INNER))

        lines.append(self._box_bottom(ROUNDS_INNER))
        return lines

    # ── Side-by-side composer ────────────────────────────────────────────

    @staticmethod
    def _side_by_side(left_lines: List[str], right_lines: List[str], gap: str = " ") -> str:
        """Combine two column lists of lines side by side.

        Args:
            left_lines: Lines for left column
            right_lines: Lines for right column
            gap: Gap string between columns

        Returns:
            Combined string
        """
        max_len = max(len(left_lines), len(right_lines))

        left_w = len(left_lines[0]) if left_lines else 0
        right_w = len(right_lines[0]) if right_lines else 0

        result = []
        for i in range(max_len):
            l_line = left_lines[i] if i < len(left_lines) else " " * left_w
            r_line = right_lines[i] if i < len(right_lines) else " " * right_w
            result.append(l_line + gap + r_line)

        return "\n".join(result)

    # ── Full screen layout ───────────────────────────────────────────────

    def render_full_screen(
        self,
        username: str,
        balance: float,
        last_number: Optional[int],
        last_color: Optional[str],
        chat_messages: List[Dict[str, Any]],
        seconds_until_spin: int,
        num_users: int,
        round_history: Optional[List[Dict[str, Any]]] = None,
        active_bets: Optional[List[Dict[str, Any]]] = None,
    ) -> str:
        """Render the full game screen.

        Layout::

            ┌─ status bar (next round + balance) ───────────────────┐
            ┌─ board ──────────────────────┐ ┌─ active bets ──┐
            │ 0 │ 3  6  9 … 36            │ │                │
            └──────────────────────────────┘ └────────────────┘
            ┌─ chat ──────────────┐ ┌─ last rounds ──┐
            │                     │ │                 │
            └─────────────────────┘ └─────────────────┘

        Returns:
            Full rendered screen
        """
        if round_history is None:
            round_history = []
        if active_bets is None:
            active_bets = []

        parts: List[str] = []

        # 1. Status bar (full width)
        parts.append(self.render_status_bar(seconds_until_spin, balance))

        # 2. Board (left) + active bets (right)
        board_lines = self.render_roulette_board(last_number, last_color)
        bets_content = len(board_lines) - 2  # minus top/bottom borders
        bets_lines = self.render_active_bets_panel(active_bets, total_lines=bets_content)
        parts.append(self._side_by_side(board_lines, bets_lines))

        # 3. Chat (left) + last rounds (right)
        chat_lines = self.render_chat_panel(chat_messages)
        rounds_content = len(chat_lines) - 2
        rounds_lines = self.render_last_rounds_panel(round_history, total_lines=rounds_content)
        parts.append(self._side_by_side(chat_lines, rounds_lines))

        return "\n".join(parts)

    # ── Legacy / utility renders ─────────────────────────────────────────

    def render_welcome(self, username: str) -> str:
        """Render welcome screen.

        Args:
            username: Username to display

        Returns:
            Rendered welcome screen
        """
        lines = []
        lines.append(self.term.bold + self.term.red("=" * 80))
        lines.append(self.term.bold + self.term.yellow("SSH ROULETTE".center(80)))
        lines.append(self.term.bold + self.term.red("=" * 80))
        lines.append("")
        lines.append(f"Welcome, {self.term.bold}{username}{self.term.normal}!")
        lines.append("")
        return "\n".join(lines)

    def render_registration(self) -> str:
        """Render registration screen.

        Returns:
            Rendered registration screen
        """
        lines = []
        lines.append(self.term.bold + self.term.red("=" * 80))
        lines.append(self.term.bold + self.term.yellow("SSH ROULETTE - REGISTRATION".center(80)))
        lines.append(self.term.bold + self.term.red("=" * 80))
        lines.append("")
        lines.append("Welcome! You are a new user.")
        lines.append("Please enter your desired username (3-20 characters, alphanumeric only):")
        lines.append("")
        return "\n".join(lines)

    def render_balance(self, balance: float) -> str:
        """Render user balance.

        Args:
            balance: Current balance

        Returns:
            Rendered balance display
        """
        return f"Balance: {self.term.bold}{self.term.green}€{balance:.2f}{self.term.normal}"

    def render_bet_options(self) -> str:
        """Render betting options.

        Returns:
            Rendered betting options
        """
        lines = []
        lines.append(self.term.bold + "Commands (use in chat with /):")
        lines.append("")
        lines.append(self.term.bold + "Bet syntax: /bet <amount> <position(s)>")
        lines.append("")
        lines.append(
            "  " + self.term.green("/bet <amt> <n>") + "           - Straight up (0-36), pays 35:1"
        )
        lines.append(
            "  " + self.term.green("/bet <amt> <n1,n2>") + "       - Split (2 numbers), pays 17:1"
        )
        lines.append(
            "  " + self.term.green("/bet <amt> <n1,n2,n3,n4>") + " - Corner (4 numbers), pays 8:1"
        )
        lines.append("  " + self.term.green("/bet <amt> <n> <n> ...") + "  - Multiple straight-ups")
        lines.append("")
        lines.append("  " + self.term.green("/bet <amt> red/black") + "    - Color bet, pays 1:1")
        lines.append(
            "  " + self.term.green("/bet <amt> even/odd") + "     - Even/odd bet, pays 1:1"
        )
        lines.append(
            "  " + self.term.green("/bet <amt> high/low") + "     - High(19-36)/low(1-18), pays 1:1"
        )
        lines.append("")
        lines.append("  " + self.term.green("/bet <amt> 1st12/2nd12/3rd12") + " - Dozens, pays 2:1")
        lines.append("  " + self.term.green("/bet <amt> col1/col2/col3") + "   - Columns, pays 2:1")
        lines.append("")
        lines.append("  " + self.term.yellow("/users") + "   - List connected users")
        lines.append("  " + self.term.yellow("/help") + "    - Show this help")
        lines.append("  " + self.term.yellow("/quit") + "    - Exit")
        lines.append("")
        lines.append("Messages without / are sent as chat to all players")
        lines.append("")
        return "\n".join(lines)

    def render_game_status(self, seconds_until_spin: int, num_users: int) -> str:
        """Render game status.

        Args:
            seconds_until_spin: Seconds until next spin
            num_users: Number of connected users

        Returns:
            Rendered status
        """
        mins = seconds_until_spin // 60
        secs = seconds_until_spin % 60

        status = f"Next spin in: {self.term.bold}{mins}:{secs:02d}{self.term.normal}"
        status += f"  |  Connected users: {self.term.bold}{num_users}{self.term.normal}"

        return status

    def render_chat(self, messages: List[Dict[str, Any]], max_lines: int = 10) -> str:
        """Render chat messages (legacy full-width version).

        Args:
            messages: List of message dicts with 'username' and 'message'
            max_lines: Maximum number of lines to display

        Returns:
            Rendered chat
        """
        lines = []
        lines.append(self.term.bold + "┌" + "─" * 78 + "┐")
        lines.append(self.term.bold + "│" + "CHAT".center(78) + "│")
        lines.append(self.term.bold + "├" + "─" * 78 + "┤")

        recent_messages = messages[-max_lines:]
        for msg in recent_messages:
            username = msg.get("username", "Unknown")
            message = msg.get("message", "")
            line = f"{self.term.cyan}{username}{self.term.normal}: {message}"
            if len(f"{username}: {message}") > 76:
                message = message[: 73 - len(username)] + "..."
                line = f"{self.term.cyan}{username}{self.term.normal}: {message}"

            padding = 76 - len(f"{username}: {message}")
            lines.append("│ " + line + " " * padding + " │")

        for _ in range(max_lines - len(recent_messages)):
            lines.append("│" + " " * 78 + "│")

        lines.append("└" + "─" * 78 + "┘")

        return "\n".join(lines)

    def render_error(self, error: str) -> str:
        """Render an error message.

        Args:
            error: Error message

        Returns:
            Rendered error
        """
        return f"{self.term.red}{self.term.bold}Error:{self.term.normal} {error}"

    def render_success(self, message: str) -> str:
        """Render a success message.

        Args:
            message: Success message

        Returns:
            Rendered success
        """
        return f"{self.term.green}{self.term.bold}✓{self.term.normal} {message}"

    def render_info(self, message: str) -> str:
        """Render an info message.

        Args:
            message: Info message

        Returns:
            Rendered info
        """
        return f"{self.term.yellow}{self.term.bold}ℹ{self.term.normal} {message}"
