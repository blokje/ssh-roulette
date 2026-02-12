"""Additional tests to improve code coverage."""

import pytest
import asyncio
import hashlib
import tempfile
from pathlib import Path
import asyncssh

from ssh_roulette.database import Database
from ssh_roulette.ssh_server import GameState, RouletteSession
from ssh_roulette.game import BetType, Bet


class MockChannel:
    """Mock SSH channel for testing."""

    def __init__(self, connection):
        self._conn = connection
        self.stdout = []
        self._closing = False
        self._exit_status = None
        self._session = None

    def get_connection(self):
        return self._conn

    def write(self, data):
        self.stdout.append(data)

    def is_closing(self):
        return self._closing

    def exit(self, status):
        self._exit_status = status
        self._closing = True

    def set_session(self, session):
        self._session = session

    def simulate_input(self, data):
        if self._session:
            self._session.data_received(data, None)

    def get_output(self):
        return "".join(self.stdout)


class MockConnection:
    """Mock SSH connection for testing."""

    def __init__(self):
        self._extra_info = {}

    def set_extra_info(self, **kwargs):
        self._extra_info.update(kwargs)

    def get_extra_info(self, name, default=None):
        return self._extra_info.get(name, default)


@pytest.fixture
async def temp_db():
    """Create a temporary database for testing."""
    with tempfile.NamedTemporaryFile(delete=False, suffix=".db") as f:
        db_path = f.name

    database = Database(db_path)
    await database.initialize()

    yield database

    Path(db_path).unlink(missing_ok=True)


@pytest.fixture
def client_key():
    """Generate a client SSH key pair for testing."""
    key = asyncssh.generate_private_key("ssh-rsa")
    return key


@pytest.fixture
async def game_state(temp_db):
    """Create a game state for testing."""
    state = GameState(temp_db)
    yield state


class TestMissingGameCoverage:
    """Tests for missing game.py coverage."""

    def test_bet_validate_dozen_invalid(self):
        """Test dozen bet with invalid value."""
        error = Bet.validate_bet("dozen", "invalid", 10.0, 100.0)
        assert error is not None
        assert "dozen" in error.lower() or "1st" in error or "2nd" in error or "3rd" in error

    def test_bet_validate_column_invalid(self):
        """Test column bet with invalid value."""
        error = Bet.validate_bet("column", "4", 10.0, 100.0)
        assert error is not None
        assert "column" in error.lower() or "1" in error and "3" in error

    def test_bet_validate_high_low_invalid(self):
        """Test high/low bet with invalid value."""
        error = Bet.validate_bet("high_low", "medium", 10.0, 100.0)
        assert error is not None
        assert "high" in error.lower() or "low" in error.lower()

    def test_bet_validate_even_odd_invalid(self):
        """Test even/odd bet with invalid value."""
        error = Bet.validate_bet("even_odd", "neither", 10.0, 100.0)
        assert error is not None
        assert "even" in error.lower() or "odd" in error.lower()

    def test_bet_calculate_payout_dozen(self):
        """Test dozen bet payout calculation."""
        bet = Bet(BetType.DOZEN, "1st", 10.0)
        payout = bet.calculate_payout(5, "red")  # Number 5 is in first dozen
        assert payout == 30.0  # 10 * 3 (2:1 payout + original bet)

    def test_bet_calculate_payout_column(self):
        """Test column bet payout calculation."""
        bet = Bet(BetType.COLUMN, "1", 10.0)
        payout = bet.calculate_payout(4, "black")  # Number 4 is in column 1
        assert payout == 30.0  # 10 * 3 (2:1 payout + original bet)


class TestMissingSSHServerCoverage:
    """Tests for missing ssh_server.py coverage."""

    @pytest.mark.asyncio
    async def test_handle_dozen_bet_command(self, game_state, client_key, temp_db):
        """Test dozen bet command."""
        key_fingerprint = hashlib.sha256(client_key.encode_ssh_public()).hexdigest()
        user_id = await temp_db.create_user("dozenuser", key_fingerprint, 100.0)

        session = RouletteSession(game_state)
        conn = MockConnection()
        conn.set_extra_info(client_public_key=client_key)

        channel = MockChannel(conn)
        session.connection_made(channel)
        channel.set_session(session)

        session.user_id = user_id
        session.username = "dozenuser"
        session.user_data = await temp_db.get_user_by_id(user_id)

        # Test dozen bet
        await session._handle_bet_command(["dozen", "1st", "20"])

        output = channel.get_output()
        assert "bet" in output.lower()

    @pytest.mark.asyncio
    async def test_handle_column_bet_command(self, game_state, client_key, temp_db):
        """Test column bet command."""
        key_fingerprint = hashlib.sha256(client_key.encode_ssh_public()).hexdigest()
        user_id = await temp_db.create_user("columnuser", key_fingerprint, 100.0)

        session = RouletteSession(game_state)
        conn = MockConnection()
        conn.set_extra_info(client_public_key=client_key)

        channel = MockChannel(conn)
        session.connection_made(channel)
        channel.set_session(session)

        session.user_id = user_id
        session.username = "columnuser"
        session.user_data = await temp_db.get_user_by_id(user_id)

        # Test column bet
        await session._handle_bet_command(["column", "2", "15"])

        output = channel.get_output()
        assert "bet" in output.lower()

    @pytest.mark.asyncio
    async def test_game_state_spin_mechanism(self, game_state):
        """Test game state spin task management."""
        # Start with no sessions
        assert game_state._spin_task is None

        # Create a mock session
        from ssh_roulette.ssh_server import RouletteSession

        session = RouletteSession(game_state)

        # Add session
        await game_state.add_session(session)

        # Spin task should be created
        assert game_state._spin_task is not None

        # Remove session
        await game_state.remove_session(session)

        # Give it time to stop
        await asyncio.sleep(0.1)

    @pytest.mark.asyncio
    async def test_invalid_bet_command_format(self, game_state, client_key, temp_db):
        """Test invalid bet command format."""
        key_fingerprint = hashlib.sha256(client_key.encode_ssh_public()).hexdigest()
        user_id = await temp_db.create_user("invaliduser", key_fingerprint, 100.0)

        session = RouletteSession(game_state)
        conn = MockConnection()
        conn.set_extra_info(client_public_key=client_key)

        channel = MockChannel(conn)
        session.connection_made(channel)
        channel.set_session(session)

        session.user_id = user_id
        session.username = "invaliduser"
        session.user_data = await temp_db.get_user_by_id(user_id)

        # Test with missing arguments
        await session._handle_bet_command(["number"])

        output = channel.get_output()
        assert "usage" in output.lower() or "error" in output.lower()

    @pytest.mark.asyncio
    async def test_username_with_special_characters(self, game_state, client_key):
        """Test registration with username containing special characters."""
        session = RouletteSession(game_state)
        conn = MockConnection()
        conn.set_extra_info(client_public_key=client_key)

        channel = MockChannel(conn)
        session.connection_made(channel)
        channel.set_session(session)

        task = asyncio.create_task(session._handle_session())
        await asyncio.sleep(0.1)

        # Try username with special characters
        channel.simulate_input("user@123!\n")
        await asyncio.sleep(0.2)

        output = channel.get_output()
        # Should show error about alphanumeric only
        assert "alphanumeric" in output.lower() or "invalid" in output.lower()

        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    @pytest.mark.asyncio
    async def test_username_too_long(self, game_state, client_key):
        """Test registration with username that's too long."""
        session = RouletteSession(game_state)
        conn = MockConnection()
        conn.set_extra_info(client_public_key=client_key)

        channel = MockChannel(conn)
        session.connection_made(channel)
        channel.set_session(session)

        task = asyncio.create_task(session._handle_session())
        await asyncio.sleep(0.1)

        # Try username that's too long (>20 characters)
        channel.simulate_input("thisusernameiswaytoolong123\n")
        await asyncio.sleep(0.2)

        output = channel.get_output()
        # Should show error about length
        assert "3-20" in output or "length" in output.lower()

        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


class TestGameStateEdgeCases:
    """Test edge cases in GameState."""

    @pytest.mark.asyncio
    async def test_get_seconds_until_spin_no_spin(self, game_state):
        """Test getting seconds until spin when no spin has occurred."""
        seconds = game_state.get_seconds_until_spin()
        # Should return 0 or spin_interval
        assert seconds >= 0

    @pytest.mark.asyncio
    async def test_broadcast_to_no_sessions(self, game_state):
        """Test broadcasting when no sessions are connected."""
        # Should not raise an error
        await game_state.broadcast_message("Test message")

    @pytest.mark.asyncio
    async def test_add_chat_message(self, game_state, temp_db):
        """Test adding chat messages."""
        user_id = await temp_db.create_user("chatter", "fp123", 100.0)

        await game_state.add_chat_message(user_id, "chatter", "Hello!")

        # Verify message was added
        messages = await temp_db.get_recent_chat_messages(10)
        assert len(messages) > 0
        assert any("Hello!" in msg["message"] for msg in messages)
