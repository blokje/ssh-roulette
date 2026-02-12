"""Integration tests for SSH Roulette server."""

import pytest
import asyncio
import asyncssh
from pathlib import Path
import tempfile
import hashlib

from ssh_roulette.database import Database
from ssh_roulette.ssh_server import GameState, RouletteServer, RouletteSession
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
    # Generate client key
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
        self.stdout = MockStream()
        self._closing = False
        self._exit_status = None
        self._session = None

    def get_connection(self):
        return self._conn

    def write(self, data):
        self.stdout.data.append(data)

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


class MockStream:
    """Mock stream for testing."""

    def __init__(self):
        self.data = []
        self._read_pos = 0

    async def readline(self):
        if self._read_pos < len(self.data):
            line = self.data[self._read_pos]
            self._read_pos += 1
            return line
        return ""

    def write(self, data):
        self.data.append(data)

    async def drain(self):
        pass


class MockConnection:
    """Mock SSH connection for testing."""

    def __init__(self):
        self._extra_info = {}

    def set_extra_info(self, **kwargs):
        self._extra_info.update(kwargs)

    def get_extra_info(self, name, default=None):
        return self._extra_info.get(name, default)


class TestSSHServerIntegration:
    """Integration tests for SSH server components."""

    @pytest.mark.asyncio
    async def test_validate_public_key_stores_key(self, game_state, client_key):
        """Test that validate_public_key stores the client key."""
        server = RouletteServer(game_state)
        conn = MockConnection()
        server._conn = conn

        # Validate a key
        result = server.validate_public_key("testuser", client_key)
        assert result is True

        # Check that key was stored
        stored_key = conn.get_extra_info("client_public_key")
        assert stored_key is not None
        assert stored_key == client_key

    @pytest.mark.asyncio
    async def test_session_retrieves_key_fingerprint(self, game_state, client_key, temp_db):
        """Test that session can retrieve and use the client key."""
        # Create a user in database
        key_fingerprint = hashlib.sha256(client_key.encode_ssh_public()).hexdigest()
        await temp_db.create_user("testuser", key_fingerprint, 100.0)

        # Create a session
        session = RouletteSession(game_state)

        # Create mock connection with stored key
        conn = MockConnection()
        conn.set_extra_info(client_public_key=client_key)

        # Create mock channel
        channel = MockChannel(conn)
        session.connection_made(channel)

        # Start session handling (this will check the key)
        # We'll let it run briefly then check if it worked
        task = asyncio.create_task(session._handle_session())

        # Give it time to process
        await asyncio.sleep(0.1)

        # Cancel the task
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

        # Check that session identified the user
        assert session.username == "testuser"
        assert session.user_id is not None

    @pytest.mark.asyncio
    async def test_session_registers_new_user(self, game_state, client_key, temp_db):
        """Test that session can register a new user."""
        # Create a session with a new key
        session = RouletteSession(game_state)

        # Create mock connection with stored key
        conn = MockConnection()
        conn.set_extra_info(client_public_key=client_key)

        # Create mock channel
        channel = MockChannel(conn)
        session.connection_made(channel)
        channel.set_session(session)

        # Start session handling
        task = asyncio.create_task(session._handle_session())

        # Give it time to show registration prompt
        await asyncio.sleep(0.1)

        # Simulate user entering username
        channel.simulate_input("newuser\n")

        # Give it time to process registration
        await asyncio.sleep(0.2)

        # Cancel the task
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

        # Check that user was registered
        key_fingerprint = hashlib.sha256(client_key.encode_ssh_public()).hexdigest()
        user = await temp_db.get_user_by_fingerprint(key_fingerprint)
        assert user is not None
        assert user["username"] == "newuser"
        assert user["balance"] == 100.0

    @pytest.mark.asyncio
    async def test_session_rejects_missing_key(self, game_state):
        """Test that session rejects connection without key."""
        # Create a session
        session = RouletteSession(game_state)

        # Create mock connection WITHOUT stored key
        conn = MockConnection()
        # Don't set client_public_key

        # Create mock channel
        channel = MockChannel(conn)
        session.connection_made(channel)

        # Start session handling
        task = asyncio.create_task(session._handle_session())

        # Give it time to process
        await asyncio.sleep(0.1)

        # Session should have exited with error
        assert channel._exit_status == 1
        assert channel._closing is True

        # Cancel the task
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    @pytest.mark.asyncio
    async def test_place_bet_updates_balance(self, game_state, client_key, temp_db):
        """Test that placing a bet updates user balance."""
        # Create a user
        key_fingerprint = hashlib.sha256(client_key.encode_ssh_public()).hexdigest()
        user_id = await temp_db.create_user("betuser", key_fingerprint, 100.0)

        # Create and setup session
        session = RouletteSession(game_state)
        conn = MockConnection()
        conn.set_extra_info(client_public_key=client_key)
        channel = MockChannel(conn)
        session.connection_made(channel)

        # Manually set user info (skip full session init)
        session.user_id = user_id
        session.username = "betuser"
        session.user_data = await temp_db.get_user_by_id(user_id)

        # Place a bet
        await session._place_bet(BetType.NUMBER, "17", "10")

        # Check balance was updated
        user = await temp_db.get_user_by_id(user_id)
        assert user["balance"] == 90.0

    @pytest.mark.asyncio
    async def test_chat_message_stored(self, game_state, client_key, temp_db):
        """Test that chat messages are stored in database."""
        # Create a user
        key_fingerprint = hashlib.sha256(client_key.encode_ssh_public()).hexdigest()
        user_id = await temp_db.create_user("chatuser", key_fingerprint, 100.0)

        # Add a chat message through game state
        await game_state.add_chat_message(user_id, "chatuser", "Hello world!")

        # Verify message was stored
        messages = await temp_db.get_recent_chat_messages(10)
        assert len(messages) >= 1
        assert any("Hello world!" in msg["message"] for msg in messages)

    @pytest.mark.asyncio
    async def test_multiple_sessions(self, game_state, client_key, temp_db):
        """Test that multiple sessions can coexist."""
        # Create two users
        key1 = asyncssh.generate_private_key("ssh-rsa")
        key2 = asyncssh.generate_private_key("ssh-rsa")

        fp1 = hashlib.sha256(key1.encode_ssh_public()).hexdigest()
        fp2 = hashlib.sha256(key2.encode_ssh_public()).hexdigest()

        await temp_db.create_user("user1", fp1, 100.0)
        await temp_db.create_user("user2", fp2, 100.0)

        # Create two sessions
        session1 = RouletteSession(game_state)
        session2 = RouletteSession(game_state)

        # Add them to game state
        await game_state.add_session(session1)
        await game_state.add_session(session2)

        # Check both are tracked
        assert len(game_state.sessions) == 2
        assert session1 in game_state.sessions
        assert session2 in game_state.sessions

        # Remove one
        await game_state.remove_session(session1)
        assert len(game_state.sessions) == 1
        assert session2 in game_state.sessions

    @pytest.mark.asyncio
    async def test_bankruptcy_reset(self, temp_db):
        """Test that bankrupt users get daily reset."""
        # Create bankrupt users
        await temp_db.create_user("bankrupt1", "fp1", 0.0)
        await temp_db.create_user("bankrupt2", "fp2", -5.0)
        await temp_db.create_user("solvent", "fp3", 50.0)

        # Run reset
        count = await temp_db.reset_bankrupt_users(10.0)
        assert count == 2

        # Check balances
        user1 = await temp_db.get_user_by_fingerprint("fp1")
        user2 = await temp_db.get_user_by_fingerprint("fp2")
        user3 = await temp_db.get_user_by_fingerprint("fp3")

        assert user1["balance"] == 10.0
        assert user2["balance"] == 10.0
        assert user3["balance"] == 50.0  # Unchanged

    @pytest.mark.asyncio
    async def test_bet_validation(self, game_state, client_key, temp_db):
        """Test bet validation with insufficient balance."""
        # Create a user with low balance
        key_fingerprint = hashlib.sha256(client_key.encode_ssh_public()).hexdigest()
        user_id = await temp_db.create_user("pooruser", key_fingerprint, 5.0)

        # Create and setup session
        session = RouletteSession(game_state)
        conn = MockConnection()
        conn.set_extra_info(client_public_key=client_key)
        channel = MockChannel(conn)
        session.connection_made(channel)

        session.user_id = user_id
        session.username = "pooruser"
        session.user_data = await temp_db.get_user_by_id(user_id)

        # Try to place a bet that's too large
        await session._place_bet(BetType.NUMBER, "17", "10")

        # Balance should be unchanged (bet rejected)
        user = await temp_db.get_user_by_id(user_id)
        assert user["balance"] == 5.0

        # Check error feedback in chat messages
        chat_text = " ".join(
            m["message"] for m in game_state.chat_messages
        ).lower()
        assert "insufficient" in chat_text or "balance" in chat_text or "rejected" in chat_text

    @pytest.mark.asyncio
    async def test_different_bet_types(self, game_state, client_key, temp_db):
        """Test placing different types of bets."""
        # Create a user with sufficient balance
        key_fingerprint = hashlib.sha256(client_key.encode_ssh_public()).hexdigest()
        user_id = await temp_db.create_user("richuser", key_fingerprint, 1000.0)

        # Create and setup session
        session = RouletteSession(game_state)
        conn = MockConnection()
        conn.set_extra_info(client_public_key=client_key)
        channel = MockChannel(conn)
        session.connection_made(channel)

        session.user_id = user_id
        session.username = "richuser"

        # Place different bet types
        bet_types = [
            (BetType.NUMBER, "17", "10"),
            (BetType.SPLIT, "5,6", "20"),
            (BetType.CORNER, "1,2,4,5", "15"),
            (BetType.COLOR, "red", "25"),
            (BetType.EVEN_ODD, "even", "10"),
            (BetType.HIGH_LOW, "high", "10"),
        ]

        for bet_type, value, amount in bet_types:
            session.user_data = await temp_db.get_user_by_id(user_id)
            await session._place_bet(bet_type, value, amount)

        # Check total deducted (10+20+15+25+10+10 = 90)
        user = await temp_db.get_user_by_id(user_id)
        assert user["balance"] == 910.0
