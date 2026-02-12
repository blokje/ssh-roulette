"""Roulette game logic."""

import random
from typing import Tuple, Optional
from enum import Enum


class BetType(Enum):
    """Types of bets in Roulette."""

    NUMBER = "number"  # Straight up bet on a single number
    SPLIT = "split"  # Bet on two adjacent numbers
    CORNER = "corner"  # Bet on four numbers at corners
    COLOR = "color"  # Red or black
    EVEN_ODD = "even_odd"  # Even or odd
    HIGH_LOW = "high_low"  # 1-18 (low) or 19-36 (high)
    DOZEN = "dozen"  # 1st 12, 2nd 12, or 3rd 12
    COLUMN = "column"  # Column bet


class RouletteWheel:
    """Roulette wheel simulation."""

    # European Roulette wheel (0-36)
    RED_NUMBERS = {1, 3, 5, 7, 9, 12, 14, 16, 18, 19, 21, 23, 25, 27, 30, 32, 34, 36}
    BLACK_NUMBERS = {2, 4, 6, 8, 10, 11, 13, 15, 17, 20, 22, 24, 26, 28, 29, 31, 33, 35}
    GREEN_NUMBERS = {0}

    @classmethod
    def spin(cls) -> Tuple[int, str]:
        """Spin the wheel and return the winning number and color.

        Returns:
            Tuple of (winning_number, winning_color)
        """
        number = random.randint(0, 36)

        if number in cls.RED_NUMBERS:
            color = "red"
        elif number in cls.BLACK_NUMBERS:
            color = "black"
        else:
            color = "green"

        return number, color

    @classmethod
    def get_color(cls, number: int) -> str:
        """Get the color of a number.

        Args:
            number: The roulette number (0-36)

        Returns:
            The color ('red', 'black', or 'green')
        """
        if number in cls.RED_NUMBERS:
            return "red"
        elif number in cls.BLACK_NUMBERS:
            return "black"
        else:
            return "green"


class Bet:
    """Represents a bet in Roulette."""

    def __init__(self, bet_type: BetType, value: str, amount: float):
        """Initialize a bet.

        Args:
            bet_type: Type of bet
            value: The value being bet on (number, color, etc.)
            amount: Amount being bet
        """
        self.bet_type = bet_type
        self.value = value
        self.amount = amount

    def calculate_payout(self, winning_number: int, winning_color: str) -> float:
        """Calculate payout for this bet.

        Args:
            winning_number: The winning number
            winning_color: The winning color

        Returns:
            Payout amount (0 if bet loses)
        """
        if self.bet_type == BetType.NUMBER:
            # Straight up bet pays 35:1
            if int(self.value) == winning_number:
                return self.amount * 36  # Original bet + 35:1 payout
            return 0.0

        elif self.bet_type == BetType.SPLIT:
            # Split bet pays 17:1
            numbers = [int(n) for n in self.value.split(",")]
            if winning_number in numbers:
                return self.amount * 18  # Original bet + 17:1 payout
            return 0.0

        elif self.bet_type == BetType.CORNER:
            # Corner bet pays 8:1
            numbers = [int(n) for n in self.value.split(",")]
            if winning_number in numbers:
                return self.amount * 9  # Original bet + 8:1 payout
            return 0.0

        elif self.bet_type == BetType.COLOR:
            # Color bet pays 1:1
            if self.value == winning_color and winning_number != 0:
                return self.amount * 2  # Original bet + 1:1 payout
            return 0.0

        elif self.bet_type == BetType.EVEN_ODD:
            # Even/Odd bet pays 1:1
            if winning_number == 0:
                return 0.0
            is_even = winning_number % 2 == 0
            if (self.value == "even" and is_even) or (self.value == "odd" and not is_even):
                return self.amount * 2
            return 0.0

        elif self.bet_type == BetType.HIGH_LOW:
            # High/Low bet pays 1:1
            if winning_number == 0:
                return 0.0
            if self.value == "low" and 1 <= winning_number <= 18:
                return self.amount * 2
            elif self.value == "high" and 19 <= winning_number <= 36:
                return self.amount * 2
            return 0.0

        elif self.bet_type == BetType.DOZEN:
            # Dozen bet pays 2:1
            if winning_number == 0:
                return 0.0
            dozen_map = {
                "1st": range(1, 13),
                "2nd": range(13, 25),
                "3rd": range(25, 37),
            }
            if winning_number in dozen_map.get(self.value, []):
                return self.amount * 3  # Original bet + 2:1 payout
            return 0.0

        elif self.bet_type == BetType.COLUMN:
            # Column bet pays 2:1
            if winning_number == 0:
                return 0.0
            column = int(self.value)
            # Column 1: 1, 4, 7, ... 34
            # Column 2: 2, 5, 8, ... 35
            # Column 3: 3, 6, 9, ... 36
            if (winning_number - column) % 3 == 0:
                return self.amount * 3
            return 0.0

        return 0.0

    @staticmethod
    def validate_bet(
        bet_type: str, value: str, amount: float, user_balance: float
    ) -> Optional[str]:
        """Validate a bet.

        Args:
            bet_type: Type of bet
            value: Bet value
            amount: Bet amount
            user_balance: User's current balance

        Returns:
            Error message if invalid, None if valid
        """
        if amount <= 0:
            return "Bet amount must be positive"

        if amount > user_balance:
            return "Insufficient balance"

        try:
            bet_type_enum = BetType(bet_type)
        except ValueError:
            return f"Invalid bet type: {bet_type}"

        if bet_type_enum == BetType.NUMBER:
            try:
                num = int(value)
                if not 0 <= num <= 36:
                    return "Number must be between 0 and 36"
            except ValueError:
                return "Invalid number"

        elif bet_type_enum == BetType.SPLIT:
            # Validate split bet (two adjacent numbers)
            try:
                numbers = [int(n.strip()) for n in value.split(",")]
                if len(numbers) != 2:
                    return "Split bet requires exactly 2 numbers (e.g., '5,6')"
                for num in numbers:
                    if not 0 <= num <= 36:
                        return "Numbers must be between 0 and 36"
                # Check if numbers are adjacent (simplified check)
                if abs(numbers[0] - numbers[1]) not in [1, 3]:
                    return "Numbers must be adjacent on the roulette table"
            except ValueError:
                return "Invalid split bet format. Use: number1,number2"

        elif bet_type_enum == BetType.CORNER:
            # Validate corner bet (four numbers at corners)
            try:
                numbers = [int(n.strip()) for n in value.split(",")]
                if len(numbers) != 4:
                    return "Corner bet requires exactly 4 numbers (e.g., '1,2,4,5')"
                for num in numbers:
                    if not 0 <= num <= 36:
                        return "Numbers must be between 0 and 36"
            except ValueError:
                return "Invalid corner bet format. Use: n1,n2,n3,n4"

        elif bet_type_enum == BetType.COLOR:
            if value not in ["red", "black"]:
                return "Color must be 'red' or 'black'"

        elif bet_type_enum == BetType.EVEN_ODD:
            if value not in ["even", "odd"]:
                return "Must be 'even' or 'odd'"

        elif bet_type_enum == BetType.HIGH_LOW:
            if value not in ["low", "high"]:
                return "Must be 'low' (1-18) or 'high' (19-36)"

        elif bet_type_enum == BetType.DOZEN:
            if value not in ["1st", "2nd", "3rd"]:
                return "Must be '1st', '2nd', or '3rd' dozen"

        elif bet_type_enum == BetType.COLUMN:
            if value not in ["1", "2", "3"]:
                return "Column must be '1', '2', or '3'"

        return None
