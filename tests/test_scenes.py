"""Scene-based tests for SSH Roulette server input/output."""

import pytest
import asyncio
import asyncssh
from pathlib import Path
import tempfile
import hashlib

from ssh_roulette.database import Database
from ssh_roulette.ssh_server import GameState, RouletteSession
from ssh_roulette.game import BetType


@pytest.fixture
async def temp_db():
    """Create a temporary database for testing."""
    with tempfile.NamedTemporaryFile(delete=False, suffix=".db") as f:
        db_path = f.name

    database = Database(db_path)
    await database.initialize()

    yield database

    # Cleanup
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
        """Store reference to session for simulating input."""
        self._session = session

    def simulate_input(self, data):
        """Simulate user input by calling data_received."""
        if self._session:
            self._session.data_received(data, None)

    def get_output(self):
        """Get all output written to channel."""
        return "".join(self.stdout)

    def clear_output(self):
        """Clear output buffer."""
        self.stdout = []


class MockConnection:
    """Mock SSH connection for testing."""

    def __init__(self):
        self._extra_info = {}

    def set_extra_info(self, **kwargs):
        self._extra_info.update(kwargs)

    def get_extra_info(self, name, default=None):
        return self._extra_info.get(name, default)


class TestRegistrationScene:
    """Test the user registration scene."""

    @pytest.mark.asyncio
    async def test_registration_prompt_shown(self, game_state, client_key, temp_db):
        """Test that registration prompt is shown for new users."""
        session = RouletteSession(game_state)
        conn = MockConnection()
        conn.set_extra_info(client_public_key=client_key)

        channel = MockChannel(conn)
        session.connection_made(channel)
        channel.set_session(session)

        # Start session
        task = asyncio.create_task(session._handle_session())
        await asyncio.sleep(0.1)

        # Check output contains registration prompt
        output = channel.get_output()
        assert "REGISTRATION" in output or "new user" in output.lower()
        assert "username" in output.lower()

        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    @pytest.mark.asyncio
    async def test_registration_username_validation_length(self, game_state, client_key, temp_db):
        """Test username validation for length."""
        session = RouletteSession(game_state)
        conn = MockConnection()
        conn.set_extra_info(client_public_key=client_key)

        channel = MockChannel(conn)
        session.connection_made(channel)
        channel.set_session(session)

        task = asyncio.create_task(session._handle_session())
        await asyncio.sleep(0.1)

        # Try invalid username (too short)
        channel.clear_output()
        channel.simulate_input("ab\n")
        await asyncio.sleep(0.1)

        output = channel.get_output()
        # Should show error or re-prompt
        assert "3-20" in output or "invalid" in output.lower() or "username" in output.lower()

        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    @pytest.mark.asyncio
    async def test_registration_success_shows_balance(self, game_state, client_key, temp_db):
        """Test successful registration shows welcome and balance."""
        session = RouletteSession(game_state)
        conn = MockConnection()
        conn.set_extra_info(client_public_key=client_key)

        channel = MockChannel(conn)
        session.connection_made(channel)
        channel.set_session(session)

        task = asyncio.create_task(session._handle_session())
        await asyncio.sleep(0.1)

        # Submit valid username
        channel.clear_output()
        channel.simulate_input("testuser\n")
        await asyncio.sleep(0.5)  # Wait longer for full processing

        output = channel.get_output()
        # Should show balance of €100
        assert "100" in output or "€100" in output

        # Verify user was created in database
        key_fingerprint = hashlib.sha256(client_key.encode_ssh_public()).hexdigest()
        user = await temp_db.get_user_by_fingerprint(key_fingerprint)
        assert user is not None
        assert user["username"] == "testuser"
        assert user["balance"] == 100.0

        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


class TestMainGameScene:
    """Test the main game scene."""

    @pytest.mark.asyncio
    async def test_game_screen_shows_roulette_board(self, game_state, client_key, temp_db):
        """Test that game screen shows roulette board."""
        # Create existing user
        key_fingerprint = hashlib.sha256(client_key.encode_ssh_public()).hexdigest()
        await temp_db.create_user("player1", key_fingerprint, 500.0)

        session = RouletteSession(game_state)
        conn = MockConnection()
        conn.set_extra_info(client_public_key=client_key)

        channel = MockChannel(conn)
        session.connection_made(channel)
        channel.set_session(session)

        task = asyncio.create_task(session._handle_session())
        await asyncio.sleep(0.2)

        output = channel.get_output()
        # Should show roulette numbers
        assert "ROULETTE" in output or any(str(i) in output for i in range(0, 37))
        # Should show balance
        assert "500" in output or "€500" in output

        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    @pytest.mark.asyncio
    async def test_bet_command_shows_confirmation(self, game_state, client_key, temp_db):
        """Test that bet command shows confirmation."""
        key_fingerprint = hashlib.sha256(client_key.encode_ssh_public()).hexdigest()
        user_id = await temp_db.create_user("betplayer", key_fingerprint, 200.0)

        session = RouletteSession(game_state)
        conn = MockConnection()
        conn.set_extra_info(client_public_key=client_key)

        channel = MockChannel(conn)
        session.connection_made(channel)
        channel.set_session(session)

        # Manually set user info (skip full session init)
        session.user_id = user_id
        session.username = "betplayer"
        session.user_data = await temp_db.get_user_by_id(user_id)

        # Place a bet
        channel.clear_output()
        await session._place_bet(BetType.NUMBER, "17", "50")

        output = channel.get_output()
        # Should show bet confirmation
        assert "bet" in output.lower() and (
            "placed" in output.lower() or "success" in output.lower()
        )
        # Should show the bet details
        assert "17" in output and "50" in output

    @pytest.mark.asyncio
    async def test_help_command_shows_all_commands(self, game_state, client_key, temp_db):
        """Test that help command shows all available commands."""
        key_fingerprint = hashlib.sha256(client_key.encode_ssh_public()).hexdigest()
        await temp_db.create_user("helpuser", key_fingerprint, 100.0)

        session = RouletteSession(game_state)
        conn = MockConnection()
        conn.set_extra_info(client_public_key=client_key)

        channel = MockChannel(conn)
        session.connection_made(channel)
        channel.set_session(session)

        task = asyncio.create_task(session._handle_session())
        await asyncio.sleep(0.1)

        # Send help command
        channel.clear_output()
        channel.simulate_input("/help\n")
        await asyncio.sleep(0.1)

        output = channel.get_output()
        # Should show bet commands
        assert "/bet" in output
        # Should show other commands
        assert "/users" in output or "/quit" in output or "/help" in output

        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    @pytest.mark.asyncio
    async def test_users_command_shows_connected_users(self, game_state, client_key, temp_db):
        """Test that users command shows list of connected users."""
        key_fingerprint = hashlib.sha256(client_key.encode_ssh_public()).hexdigest()
        user_id = await temp_db.create_user("listplayer", key_fingerprint, 100.0)

        session = RouletteSession(game_state)
        conn = MockConnection()
        conn.set_extra_info(client_public_key=client_key)

        channel = MockChannel(conn)
        session.connection_made(channel)
        channel.set_session(session)

        # Set up session
        session.user_id = user_id
        session.username = "listplayer"
        await game_state.add_session(session)

        # Request users list
        channel.clear_output()
        await session._show_users()

        output = channel.get_output()
        # Should show connected users header
        assert "connected" in output.lower() or "users" in output.lower()
        # Should show the username
        assert "listplayer" in output

        await game_state.remove_session(session)

    @pytest.mark.asyncio
    async def test_chat_message_displays(self, game_state, client_key, temp_db):
        """Test that chat messages are displayed."""
        key_fingerprint = hashlib.sha256(client_key.encode_ssh_public()).hexdigest()
        user_id = await temp_db.create_user("chatter", key_fingerprint, 100.0)

        # Add a chat message
        await game_state.add_chat_message(user_id, "chatter", "Hello world!")

        session = RouletteSession(game_state)
        conn = MockConnection()
        conn.set_extra_info(client_public_key=client_key)

        channel = MockChannel(conn)
        session.connection_made(channel)
        channel.set_session(session)

        # Set up session
        session.user_id = user_id
        session.username = "chatter"
        session.user_data = await temp_db.get_user_by_id(user_id)

        # Refresh display (should show chat)
        channel.clear_output()
        await session.refresh_display()

        output = channel.get_output()
        # Should contain the chat message
        assert "Hello world!" in output or "chatter" in output


class TestErrorHandlingScenes:
    """Test error handling in various scenes."""

    @pytest.mark.asyncio
    async def test_invalid_bet_type_shows_error(self, game_state, client_key, temp_db):
        """Test that invalid bet type shows error message."""
        key_fingerprint = hashlib.sha256(client_key.encode_ssh_public()).hexdigest()
        user_id = await temp_db.create_user("erroruser", key_fingerprint, 100.0)

        session = RouletteSession(game_state)
        conn = MockConnection()
        conn.set_extra_info(client_public_key=client_key)

        channel = MockChannel(conn)
        session.connection_made(channel)
        channel.set_session(session)

        session.user_id = user_id
        session.username = "erroruser"
        session.user_data = await temp_db.get_user_by_id(user_id)

        # Try invalid bet type
        channel.clear_output()
        await session._handle_bet_command(["invalid", "10", "10"])

        output = channel.get_output()
        # Should show error
        assert (
            "error" in output.lower() or "invalid" in output.lower() or "unknown" in output.lower()
        )

    @pytest.mark.asyncio
    async def test_insufficient_balance_shows_error(self, game_state, client_key, temp_db):
        """Test that insufficient balance shows error."""
        key_fingerprint = hashlib.sha256(client_key.encode_ssh_public()).hexdigest()
        user_id = await temp_db.create_user("pooruser", key_fingerprint, 5.0)

        session = RouletteSession(game_state)
        conn = MockConnection()
        conn.set_extra_info(client_public_key=client_key)

        channel = MockChannel(conn)
        session.connection_made(channel)
        channel.set_session(session)

        session.user_id = user_id
        session.username = "pooruser"
        session.user_data = await temp_db.get_user_by_id(user_id)

        # Try to bet more than balance
        channel.clear_output()
        await session._place_bet(BetType.NUMBER, "17", "100")

        output = channel.get_output()
        # Should show insufficient balance error
        assert "insufficient" in output.lower() or "balance" in output.lower()

    @pytest.mark.asyncio
    async def test_invalid_bet_number_shows_error(self, game_state, client_key, temp_db):
        """Test that invalid bet number shows error."""
        key_fingerprint = hashlib.sha256(client_key.encode_ssh_public()).hexdigest()
        user_id = await temp_db.create_user("player", key_fingerprint, 100.0)

        session = RouletteSession(game_state)
        conn = MockConnection()
        conn.set_extra_info(client_public_key=client_key)

        channel = MockChannel(conn)
        session.connection_made(channel)
        channel.set_session(session)

        session.user_id = user_id
        session.username = "player"
        session.user_data = await temp_db.get_user_by_id(user_id)

        # Try invalid number (out of range)
        channel.clear_output()
        await session._place_bet(BetType.NUMBER, "99", "10")

        output = channel.get_output()
        # Should show error
        assert (
            "error" in output.lower()
            or "invalid" in output.lower()
            or "0" in output
            and "36" in output
        )


class TestBetCommandVariations:
    """Test different bet command input/output variations."""

    @pytest.mark.asyncio
    async def test_split_bet_shows_correct_format(self, game_state, client_key, temp_db):
        """Test split bet command output."""
        key_fingerprint = hashlib.sha256(client_key.encode_ssh_public()).hexdigest()
        user_id = await temp_db.create_user("splitplayer", key_fingerprint, 200.0)

        session = RouletteSession(game_state)
        conn = MockConnection()
        conn.set_extra_info(client_public_key=client_key)

        channel = MockChannel(conn)
        session.connection_made(channel)
        channel.set_session(session)

        session.user_id = user_id
        session.username = "splitplayer"
        session.user_data = await temp_db.get_user_by_id(user_id)

        # Place split bet
        channel.clear_output()
        await session._place_bet(BetType.SPLIT, "5,6", "20")

        output = channel.get_output()
        # Should show bet confirmation with split details
        assert "bet" in output.lower() and ("5,6" in output or ("5" in output and "6" in output))

    @pytest.mark.asyncio
    async def test_corner_bet_shows_correct_format(self, game_state, client_key, temp_db):
        """Test corner bet command output."""
        key_fingerprint = hashlib.sha256(client_key.encode_ssh_public()).hexdigest()
        user_id = await temp_db.create_user("cornerplayer", key_fingerprint, 200.0)

        session = RouletteSession(game_state)
        conn = MockConnection()
        conn.set_extra_info(client_public_key=client_key)

        channel = MockChannel(conn)
        session.connection_made(channel)
        channel.set_session(session)

        session.user_id = user_id
        session.username = "cornerplayer"
        session.user_data = await temp_db.get_user_by_id(user_id)

        # Place corner bet
        channel.clear_output()
        await session._place_bet(BetType.CORNER, "1,2,4,5", "15")

        output = channel.get_output()
        # Should show bet confirmation
        assert "bet" in output.lower() and ("1,2,4,5" in output or "corner" in output.lower())

    @pytest.mark.asyncio
    async def test_color_bet_shows_correct_format(self, game_state, client_key, temp_db):
        """Test color bet command output."""
        key_fingerprint = hashlib.sha256(client_key.encode_ssh_public()).hexdigest()
        user_id = await temp_db.create_user("colorplayer", key_fingerprint, 200.0)

        session = RouletteSession(game_state)
        conn = MockConnection()
        conn.set_extra_info(client_public_key=client_key)

        channel = MockChannel(conn)
        session.connection_made(channel)
        channel.set_session(session)

        session.user_id = user_id
        session.username = "colorplayer"
        session.user_data = await temp_db.get_user_by_id(user_id)

        # Place color bet
        channel.clear_output()
        await session._place_bet(BetType.COLOR, "red", "25")

        output = channel.get_output()
        # Should show bet confirmation with color
        assert "bet" in output.lower() and "red" in output.lower()


class TestSessionLifecycle:
    """Test session lifecycle scenes."""

    @pytest.mark.asyncio
    async def test_quit_command_shows_goodbye(self, game_state, client_key, temp_db):
        """Test that quit command shows goodbye message."""
        key_fingerprint = hashlib.sha256(client_key.encode_ssh_public()).hexdigest()
        await temp_db.create_user("quitter", key_fingerprint, 100.0)

        session = RouletteSession(game_state)
        conn = MockConnection()
        conn.set_extra_info(client_public_key=client_key)

        channel = MockChannel(conn)
        session.connection_made(channel)
        channel.set_session(session)

        task = asyncio.create_task(session._handle_session())
        await asyncio.sleep(0.1)

        # Send quit command
        channel.clear_output()
        channel.simulate_input("/quit\n")
        await asyncio.sleep(0.1)

        output = channel.get_output()
        # Should show goodbye message
        assert "goodbye" in output.lower() or "exit" in output.lower()

        # Session should be marked to exit
        assert session._should_exit is True

        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    @pytest.mark.asyncio
    async def test_missing_key_shows_error_and_exits(self, game_state):
        """Test that missing SSH key shows error and exits."""
        session = RouletteSession(game_state)
        conn = MockConnection()
        # Don't set client_public_key

        channel = MockChannel(conn)
        session.connection_made(channel)
        channel.set_session(session)

        task = asyncio.create_task(session._handle_session())
        await asyncio.sleep(0.1)

        output = channel.get_output()
        # Should show error about missing key
        assert "key" in output.lower() or "error" in output.lower()
        # Should have exited
        assert channel._exit_status == 1

        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
