"""Terminal User Interface for SSH Roulette."""

from blessed import Terminal
from typing import List, Dict, Any, Optional
from datetime import datetime


class RouletteTUI:
    """Terminal User Interface for Roulette game."""

    def __init__(self):
        """Initialize the TUI."""
        self.term = Terminal()
        self.width = 80
        self.height = 24

    def clear(self) -> str:
        """Clear the screen.
        
        Returns:
            ANSI escape codes to clear screen
        """
        return self.term.clear()

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

    def render_roulette_board(self, last_number: Optional[int] = None, last_color: Optional[str] = None) -> str:
        """Render the roulette board.
        
        Args:
            last_number: Last winning number
            last_color: Last winning color
            
        Returns:
            Rendered board
        """
        lines = []
        
        # Header
        lines.append(self.term.bold + "┌" + "─" * 78 + "┐")
        lines.append(self.term.bold + "│" + "ROULETTE BOARD".center(78) + "│")
        lines.append(self.term.bold + "├" + "─" * 78 + "┤")
        
        # Last result
        if last_number is not None:
            color_code = ""
            if last_color == "red":
                color_code = self.term.red
            elif last_color == "black":
                color_code = self.term.white
            else:
                color_code = self.term.green
            
            result = f"Last: {color_code}{self.term.bold}{last_number}{self.term.normal} ({last_color})"
            lines.append("│ " + result + " " * (76 - len(f"Last: {last_number} ({last_color})")) + " │")
        else:
            lines.append("│ " + "Waiting for first spin...".ljust(76) + " │")
        
        lines.append("├" + "─" * 78 + "┤")
        
        # Number grid (simplified)
        # Row 1: 3, 6, 9, 12, 15, 18, 21, 24, 27, 30, 33, 36
        # Row 2: 2, 5, 8, 11, 14, 17, 20, 23, 26, 29, 32, 35
        # Row 3: 1, 4, 7, 10, 13, 16, 19, 22, 25, 28, 31, 34
        # 0 on the side
        
        from ssh_roulette.game import RouletteWheel
        
        lines.append("│ " + " 0 ".ljust(76) + " │")
        
        for row in [3, 2, 1]:
            row_nums = []
            for col in range(12):
                num = row + (col * 3)
                color = RouletteWheel.get_color(num)
                if color == "red":
                    row_nums.append(self.term.red(f"{num:2d}"))
                elif color == "black":
                    row_nums.append(self.term.white(f"{num:2d}"))
                else:
                    row_nums.append(f"{num:2d}")
            
            lines.append("│ " + " ".join(row_nums) + "  │")
        
        lines.append("└" + "─" * 78 + "┘")
        
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
        lines.append(self.term.bold + "Betting Options:")
        lines.append("")
        lines.append("  " + self.term.green("n") + " <number> <amount>  - Bet on a number (0-36), pays 35:1")
        lines.append("  " + self.term.green("c") + " <color> <amount>   - Bet on red/black, pays 1:1")
        lines.append("  " + self.term.green("e") + " <even/odd> <amount> - Bet on even/odd, pays 1:1")
        lines.append("  " + self.term.green("h") + " <high/low> <amount> - Bet on high(19-36)/low(1-18), pays 1:1")
        lines.append("")
        lines.append("  " + self.term.yellow("chat") + " <message>        - Send a chat message")
        lines.append("  " + self.term.yellow("users") + "                  - List connected users")
        lines.append("  " + self.term.yellow("help") + "                   - Show this help")
        lines.append("  " + self.term.yellow("quit") + "                   - Exit")
        lines.append("")
        return "\n".join(lines)

    def render_chat(self, messages: List[Dict[str, Any]], max_lines: int = 10) -> str:
        """Render chat messages.
        
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
            # Truncate if too long
            if len(f"{username}: {message}") > 76:
                message = message[:73 - len(username)] + "..."
                line = f"{self.term.cyan}{username}{self.term.normal}: {message}"
            
            padding = 76 - len(f"{username}: {message}")
            lines.append("│ " + line + " " * padding + " │")
        
        # Fill empty lines
        for _ in range(max_lines - len(recent_messages)):
            lines.append("│" + " " * 78 + "│")
        
        lines.append("└" + "─" * 78 + "┘")
        
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

    def render_full_screen(
        self,
        username: str,
        balance: float,
        last_number: Optional[int],
        last_color: Optional[str],
        chat_messages: List[Dict[str, Any]],
        seconds_until_spin: int,
        num_users: int,
    ) -> str:
        """Render the full game screen.
        
        Args:
            username: Current username
            balance: Current balance
            last_number: Last winning number
            last_color: Last winning color
            chat_messages: Chat messages
            seconds_until_spin: Seconds until next spin
            num_users: Number of connected users
            
        Returns:
            Full rendered screen
        """
        lines = []
        
        # Welcome header
        lines.append(self.render_welcome(username))
        
        # Balance
        lines.append(self.render_balance(balance))
        lines.append("")
        
        # Roulette board
        lines.append(self.render_roulette_board(last_number, last_color))
        lines.append("")
        
        # Game status
        lines.append(self.render_game_status(seconds_until_spin, num_users))
        lines.append("")
        
        # Chat
        lines.append(self.render_chat(chat_messages))
        lines.append("")
        
        # Bet options
        lines.append(self.render_bet_options())
        
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
