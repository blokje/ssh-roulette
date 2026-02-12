# SSH Roulette 🎰

An SSH-based Roulette game service with a beautiful Terminal User Interface (TUI). Connect via SSH and play European Roulette with other players in real-time!

## Features

- 🎲 **European Roulette**: Full roulette game with 0-36 numbers
- 🖥️ **Beautiful TUI**: Rich terminal interface using blessed
- 💬 **Live Chat**: Chat with other players in real-time
- 🔐 **SSH Key Authentication**: Secure authentication using SSH keys
- 💰 **Persistent Balances**: User accounts and balances stored in SQLite
- 🎁 **Bankruptcy Protection**: Get €10 each day if you go broke
- ⏰ **Auto-spin**: Ball spins every 5 minutes when players are connected
- 🧪 **Comprehensive Tests**: Full test coverage with pytest
- 🚀 **CI/CD Pipeline**: Automated testing and linting with GitHub Actions

## Quick Start

### Prerequisites

- Python 3.9 or higher
- [uv](https://github.com/astral-sh/uv) package manager

### Installation

1. Clone the repository:
```bash
git clone https://github.com/blokje/ssh-roulette.git
cd ssh-roulette
```

2. Install dependencies using uv:
```bash
uv sync
```

3. Run the server:
```bash
uv run ssh-roulette
```

The server will start on port 2222 by default.

### Connecting to the Server

Connect using SSH:
```bash
ssh -p 2222 localhost
```

On first connection, you'll be prompted to register a username. You'll receive €100 as starting balance.

## Usage

### Game Commands

Once connected, you can use the following commands:

#### Betting Commands

All bets use the simplified syntax: `/bet <amount> <position(s)>`

**Single Number Bets:**
- `/bet <amount> <n>` - Straight up bet on number (0-36), pays 35:1
  - Example: `/bet 10 17` (bet €10 on number 17)

**Multiple Number Bets:**
- `/bet <amount> <n1,n2>` - Split bet on 2 adjacent numbers, pays 17:1
  - Example: `/bet 20 5,6` (bet €20 on numbers 5 and 6)

- `/bet <amount> <n1,n2,n3,n4>` - Corner bet on 4 corner numbers, pays 8:1
  - Example: `/bet 15 1,2,4,5` (bet €15 on the corner 1,2,4,5)

- `/bet <amount> <n> <n> ...` - Multiple straight-up bets with same amount
  - Example: `/bet 5 17 23 8` (bet €5 on each of 17, 23, and 8)

**Even Chance Bets (1:1 payout):**
- `/bet <amount> red` or `/bet <amount> black` - Color bet
  - Example: `/bet 20 red` (bet €20 on red)

- `/bet <amount> even` or `/bet <amount> odd` - Even/odd bet
  - Example: `/bet 15 even` (bet €15 on even)

- `/bet <amount> high` or `/bet <amount> low` - High (19-36) / Low (1-18) bet
  - Example: `/bet 25 high` (bet €25 on high numbers)

**Group Bets (2:1 payout):**
- `/bet <amount> 1st12` / `2nd12` / `3rd12` - Dozen bets (groups of 12)
  - Example: `/bet 30 1st12` (bet €30 on numbers 1-12)

- `/bet <amount> col1` / `col2` / `col3` - Column bets
  - Example: `/bet 25 col1` (bet €25 on column 1)

#### Other Commands

- **Chat**: Simply type a message without `/` to send it to all connected players
  - Example: `Hello everyone!`
- `/users` - List all connected players
- `/help` - Show help message
- `/quit` - Exit the game

### Game Mechanics

- **Starting Balance**: New users receive €100
- **Auto-spin**: The wheel spins automatically every 5 minutes when at least one user is connected
- **Bankruptcy Reset**: If your balance reaches €0, you'll receive €10 the next day
- **Bet Types**: Support for straight-up, color, even/odd, high/low, dozen, and column bets

## Development

### Running Tests

Run the test suite:
```bash
uv run pytest
```

With coverage:
```bash
uv run pytest --cov=ssh_roulette --cov-report=term
```

### Code Quality

Format code with black:
```bash
uv run black ssh_roulette tests
```

Lint with flake8:
```bash
uv run flake8 ssh_roulette tests --max-line-length=100
```

Type check with mypy:
```bash
uv run mypy ssh_roulette
```

### Server Options

Run the server with custom options:
```bash
uv run ssh-roulette --host 0.0.0.0 --port 2222 --db roulette.db
```

Options:
- `--host` - Host to bind to (default: 0.0.0.0)
- `--port` - Port to bind to (default: 2222)
- `--db` - Database file path (default: roulette.db)
- `--host-key` - SSH host key file (default: host_key)

## Architecture

### Components

1. **Database Layer** (`database.py`): SQLite database with async operations
   - User management
   - Game history
   - Chat messages
   - Bet tracking

2. **Game Logic** (`game.py`): Core roulette game mechanics
   - Wheel simulation
   - Bet validation
   - Payout calculation

3. **SSH Server** (`ssh_server.py`): AsyncSSH-based server
   - SSH key authentication
   - Session management
   - Game state coordination

4. **TUI** (`tui.py`): Terminal User Interface
   - Roulette board rendering
   - Chat display
   - Status information

### Database Schema

- **users**: User accounts with SSH key fingerprints and balances
- **games**: Game history with winning numbers
- **bets**: Individual bet records
- **chat_messages**: Chat message history

## CI/CD

The project includes a GitHub Actions workflow that:
- Runs code formatting checks (black)
- Performs linting (flake8)
- Executes type checking (mypy)
- Runs the full test suite with coverage
- Performs security scanning

## License

MIT License - feel free to use and modify!

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.