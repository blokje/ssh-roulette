"""Tests for Roulette game logic."""

import pytest
from ssh_roulette.game import RouletteWheel, Bet, BetType


class TestRouletteWheel:
    """Tests for RouletteWheel class."""

    def test_spin_returns_valid_number(self):
        """Test that spin returns a number between 0 and 36."""
        for _ in range(100):
            number, color = RouletteWheel.spin()
            assert 0 <= number <= 36
            assert color in ["red", "black", "green"]

    def test_get_color_red_numbers(self):
        """Test that red numbers return red color."""
        for num in RouletteWheel.RED_NUMBERS:
            assert RouletteWheel.get_color(num) == "red"

    def test_get_color_black_numbers(self):
        """Test that black numbers return black color."""
        for num in RouletteWheel.BLACK_NUMBERS:
            assert RouletteWheel.get_color(num) == "black"

    def test_get_color_zero(self):
        """Test that zero returns green color."""
        assert RouletteWheel.get_color(0) == "green"

    def test_all_numbers_have_color(self):
        """Test that all numbers 0-36 have a defined color."""
        for num in range(37):
            color = RouletteWheel.get_color(num)
            assert color in ["red", "black", "green"]


class TestBet:
    """Tests for Bet class."""

    def test_number_bet_win(self):
        """Test winning number bet pays 35:1."""
        bet = Bet(BetType.NUMBER, "17", 10.0)
        payout = bet.calculate_payout(17, "red")
        assert payout == 360.0  # 10 * 36

    def test_number_bet_loss(self):
        """Test losing number bet pays nothing."""
        bet = Bet(BetType.NUMBER, "17", 10.0)
        payout = bet.calculate_payout(18, "red")
        assert payout == 0.0

    def test_color_bet_red_win(self):
        """Test winning red bet pays 1:1."""
        bet = Bet(BetType.COLOR, "red", 10.0)
        payout = bet.calculate_payout(1, "red")  # 1 is red
        assert payout == 20.0  # 10 * 2

    def test_color_bet_black_win(self):
        """Test winning black bet pays 1:1."""
        bet = Bet(BetType.COLOR, "black", 10.0)
        payout = bet.calculate_payout(2, "black")  # 2 is black
        assert payout == 20.0

    def test_color_bet_loss(self):
        """Test losing color bet pays nothing."""
        bet = Bet(BetType.COLOR, "red", 10.0)
        payout = bet.calculate_payout(2, "black")
        assert payout == 0.0

    def test_color_bet_zero_loses(self):
        """Test color bet loses on zero."""
        bet = Bet(BetType.COLOR, "red", 10.0)
        payout = bet.calculate_payout(0, "green")
        assert payout == 0.0

    def test_even_bet_win(self):
        """Test winning even bet pays 1:1."""
        bet = Bet(BetType.EVEN_ODD, "even", 10.0)
        payout = bet.calculate_payout(2, "black")
        assert payout == 20.0

    def test_odd_bet_win(self):
        """Test winning odd bet pays 1:1."""
        bet = Bet(BetType.EVEN_ODD, "odd", 10.0)
        payout = bet.calculate_payout(1, "red")
        assert payout == 20.0

    def test_even_odd_zero_loses(self):
        """Test even/odd bet loses on zero."""
        bet = Bet(BetType.EVEN_ODD, "even", 10.0)
        payout = bet.calculate_payout(0, "green")
        assert payout == 0.0

    def test_low_bet_win(self):
        """Test winning low bet (1-18) pays 1:1."""
        bet = Bet(BetType.HIGH_LOW, "low", 10.0)
        payout = bet.calculate_payout(10, "black")
        assert payout == 20.0

    def test_high_bet_win(self):
        """Test winning high bet (19-36) pays 1:1."""
        bet = Bet(BetType.HIGH_LOW, "high", 10.0)
        payout = bet.calculate_payout(25, "red")
        assert payout == 20.0

    def test_high_low_zero_loses(self):
        """Test high/low bet loses on zero."""
        bet = Bet(BetType.HIGH_LOW, "low", 10.0)
        payout = bet.calculate_payout(0, "green")
        assert payout == 0.0

    def test_dozen_first_win(self):
        """Test winning first dozen bet pays 2:1."""
        bet = Bet(BetType.DOZEN, "1st", 10.0)
        payout = bet.calculate_payout(5, "red")
        assert payout == 30.0  # 10 * 3

    def test_dozen_second_win(self):
        """Test winning second dozen bet pays 2:1."""
        bet = Bet(BetType.DOZEN, "2nd", 10.0)
        payout = bet.calculate_payout(15, "black")
        assert payout == 30.0

    def test_dozen_third_win(self):
        """Test winning third dozen bet pays 2:1."""
        bet = Bet(BetType.DOZEN, "3rd", 10.0)
        payout = bet.calculate_payout(30, "red")
        assert payout == 30.0

    def test_dozen_zero_loses(self):
        """Test dozen bet loses on zero."""
        bet = Bet(BetType.DOZEN, "1st", 10.0)
        payout = bet.calculate_payout(0, "green")
        assert payout == 0.0

    def test_column_bet_win(self):
        """Test winning column bet pays 2:1."""
        bet = Bet(BetType.COLUMN, "1", 10.0)
        # Column 1: 1, 4, 7, 10, 13, 16, 19, 22, 25, 28, 31, 34
        payout = bet.calculate_payout(1, "red")
        assert payout == 30.0

    def test_column_bet_loss(self):
        """Test losing column bet pays nothing."""
        bet = Bet(BetType.COLUMN, "1", 10.0)
        payout = bet.calculate_payout(2, "black")
        assert payout == 0.0

    def test_validate_bet_negative_amount(self):
        """Test that negative bet amounts are invalid."""
        error = Bet.validate_bet("number", "17", -10.0, 100.0)
        assert error == "Bet amount must be positive"

    def test_validate_bet_insufficient_balance(self):
        """Test that bets exceeding balance are invalid."""
        error = Bet.validate_bet("number", "17", 150.0, 100.0)
        assert error == "Insufficient balance"

    def test_validate_bet_invalid_type(self):
        """Test that invalid bet types are rejected."""
        error = Bet.validate_bet("invalid", "17", 10.0, 100.0)
        assert "Invalid bet type" in error

    def test_validate_bet_invalid_number_range(self):
        """Test that numbers outside 0-36 are invalid."""
        error = Bet.validate_bet("number", "37", 10.0, 100.0)
        assert "between 0 and 36" in error

    def test_validate_bet_invalid_number_format(self):
        """Test that non-numeric number values are invalid."""
        error = Bet.validate_bet("number", "abc", 10.0, 100.0)
        assert "Invalid number" in error

    def test_validate_bet_invalid_color(self):
        """Test that invalid colors are rejected."""
        error = Bet.validate_bet("color", "blue", 10.0, 100.0)
        assert "red" in error or "black" in error

    def test_validate_bet_valid_number(self):
        """Test that valid number bets pass validation."""
        error = Bet.validate_bet("number", "17", 10.0, 100.0)
        assert error is None

    def test_validate_bet_valid_color(self):
        """Test that valid color bets pass validation."""
        error = Bet.validate_bet("color", "red", 10.0, 100.0)
        assert error is None
