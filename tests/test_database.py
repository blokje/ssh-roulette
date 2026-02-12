"""Tests for database operations."""

import pytest
import asyncio
from pathlib import Path
import tempfile
from datetime import datetime, timedelta

from ssh_roulette.database import Database


@pytest.fixture
async def db():
    """Create a temporary database for testing."""
    with tempfile.NamedTemporaryFile(delete=False, suffix=".db") as f:
        db_path = f.name
    
    database = Database(db_path)
    await database.initialize()
    
    yield database
    
    # Cleanup
    Path(db_path).unlink(missing_ok=True)


class TestDatabase:
    """Tests for Database class."""

    @pytest.mark.asyncio
    async def test_initialize_creates_tables(self, db):
        """Test that initialize creates all required tables."""
        # Just verify no errors occur and we can query tables
        users = await db.get_all_users()
        assert users == []

    @pytest.mark.asyncio
    async def test_create_user(self, db):
        """Test creating a new user."""
        user_id = await db.create_user("testuser", "fingerprint123", 100.0)
        assert user_id is not None
        
        user = await db.get_user_by_id(user_id)
        assert user["username"] == "testuser"
        assert user["ssh_key_fingerprint"] == "fingerprint123"
        assert user["balance"] == 100.0

    @pytest.mark.asyncio
    async def test_create_user_duplicate_username(self, db):
        """Test that duplicate usernames are rejected."""
        await db.create_user("testuser", "fingerprint1", 100.0)
        user_id = await db.create_user("testuser", "fingerprint2", 100.0)
        assert user_id is None

    @pytest.mark.asyncio
    async def test_create_user_duplicate_fingerprint(self, db):
        """Test that duplicate fingerprints are rejected."""
        await db.create_user("user1", "fingerprint123", 100.0)
        user_id = await db.create_user("user2", "fingerprint123", 100.0)
        assert user_id is None

    @pytest.mark.asyncio
    async def test_get_user_by_fingerprint(self, db):
        """Test retrieving user by SSH key fingerprint."""
        await db.create_user("testuser", "fingerprint123", 100.0)
        
        user = await db.get_user_by_fingerprint("fingerprint123")
        assert user is not None
        assert user["username"] == "testuser"

    @pytest.mark.asyncio
    async def test_get_user_by_fingerprint_not_found(self, db):
        """Test that non-existent fingerprint returns None."""
        user = await db.get_user_by_fingerprint("nonexistent")
        assert user is None

    @pytest.mark.asyncio
    async def test_update_user_balance(self, db):
        """Test updating user balance."""
        user_id = await db.create_user("testuser", "fingerprint123", 100.0)
        
        await db.update_user_balance(user_id, 150.0)
        
        user = await db.get_user_by_id(user_id)
        assert user["balance"] == 150.0

    @pytest.mark.asyncio
    async def test_create_game(self, db):
        """Test creating a game record."""
        game_id = await db.create_game(17, "red")
        assert game_id is not None
        assert game_id > 0

    @pytest.mark.asyncio
    async def test_create_bet(self, db):
        """Test creating a bet."""
        user_id = await db.create_user("testuser", "fingerprint123", 100.0)
        game_id = await db.create_game(17, "red")
        
        bet_id = await db.create_bet(user_id, game_id, "number", "17", 10.0)
        assert bet_id is not None
        assert bet_id > 0

    @pytest.mark.asyncio
    async def test_get_game_bets(self, db):
        """Test retrieving bets for a game."""
        user_id = await db.create_user("testuser", "fingerprint123", 100.0)
        game_id = await db.create_game(17, "red")
        
        await db.create_bet(user_id, game_id, "number", "17", 10.0)
        await db.create_bet(user_id, game_id, "color", "red", 20.0)
        
        bets = await db.get_game_bets(game_id)
        assert len(bets) == 2

    @pytest.mark.asyncio
    async def test_add_chat_message(self, db):
        """Test adding a chat message."""
        user_id = await db.create_user("testuser", "fingerprint123", 100.0)
        
        msg_id = await db.add_chat_message(user_id, "Hello, world!")
        assert msg_id is not None
        assert msg_id > 0

    @pytest.mark.asyncio
    async def test_get_recent_chat_messages(self, db):
        """Test retrieving recent chat messages."""
        user_id = await db.create_user("testuser", "fingerprint123", 100.0)
        
        await db.add_chat_message(user_id, "Message 1")
        await db.add_chat_message(user_id, "Message 2")
        await db.add_chat_message(user_id, "Message 3")
        
        messages = await db.get_recent_chat_messages(10)
        assert len(messages) == 3
        assert messages[0]["message"] == "Message 1"
        assert messages[0]["username"] == "testuser"

    @pytest.mark.asyncio
    async def test_get_recent_chat_messages_limit(self, db):
        """Test that message limit is respected."""
        user_id = await db.create_user("testuser", "fingerprint123", 100.0)
        
        for i in range(10):
            await db.add_chat_message(user_id, f"Message {i}")
        
        messages = await db.get_recent_chat_messages(5)
        assert len(messages) == 5
        assert messages[0]["message"] == "Message 5"

    @pytest.mark.asyncio
    async def test_reset_bankrupt_users(self, db):
        """Test resetting bankrupt users."""
        # Create users with zero balance
        user1 = await db.create_user("user1", "fp1", 0.0)
        user2 = await db.create_user("user2", "fp2", -5.0)
        user3 = await db.create_user("user3", "fp3", 50.0)
        
        # Reset bankrupt users
        count = await db.reset_bankrupt_users(10.0)
        assert count == 2
        
        # Check balances
        u1 = await db.get_user_by_id(user1)
        u2 = await db.get_user_by_id(user2)
        u3 = await db.get_user_by_id(user3)
        
        assert u1["balance"] == 10.0
        assert u2["balance"] == 10.0
        assert u3["balance"] == 50.0  # Unchanged

    @pytest.mark.asyncio
    async def test_reset_bankrupt_users_only_once_per_day(self, db):
        """Test that users are only reset once per day."""
        user_id = await db.create_user("user1", "fp1", 0.0)
        
        # First reset
        count1 = await db.reset_bankrupt_users(10.0)
        assert count1 == 1
        
        # Second reset on same day - should not reset again
        count2 = await db.reset_bankrupt_users(10.0)
        assert count2 == 0
        
        user = await db.get_user_by_id(user_id)
        assert user["balance"] == 10.0  # Still 10, not 20

    @pytest.mark.asyncio
    async def test_get_all_users(self, db):
        """Test retrieving all users."""
        await db.create_user("alice", "fp1", 100.0)
        await db.create_user("bob", "fp2", 200.0)
        await db.create_user("charlie", "fp3", 150.0)
        
        users = await db.get_all_users()
        assert len(users) == 3
        
        # Should be sorted by username
        assert users[0]["username"] == "alice"
        assert users[1]["username"] == "bob"
        assert users[2]["username"] == "charlie"
