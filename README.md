<p align="center">
  <code>shelltrix</code> — a premium Matrix TUI client
</p>

<p align="center">
  <img src="https://img.shields.io/badge/python-3.10%2B-blue" alt="Python 3.10+" />
  <img src="https://img.shields.io/badge/license-MIT-green" alt="MIT License" />
  <img src="https://img.shields.io/badge/matrix--nio-E2EE-purple" alt="E2EE via matrix-nio" />
</p>

---

**shelltrix** is a terminal-based Matrix client built on
[`matrix-nio`](https://github.com/matrix-nio/matrix-nio) (E2EE via libolm)
and [`Textual`](https://textual.textualize.io/) (modern TUI framework).

A daily-driver replacement for gomuks / iamb, designed to be fast,
customizable, and fully owned by you — every behavior lives in this repo.

---

## Install

**Linux / macOS** with **Python >= 3.10** required.

```bash
curl -fsSL https://raw.githubusercontent.com/Nawal-alao/shelltrix/main/install.sh | sh
```

The installer handles `libolm`, `pipx`, and the shelltrix package in one step.

Verify:

```bash
shelltrix --version
```

### Manual install

```bash
# 1. libolm (pick one)
#    macOS         brew install libolm
#    Debian/Ubuntu sudo apt-get install -y libolm-dev
#    Fedora        sudo dnf install -y libolm-devel
#    Arch          sudo pacman -S --noconfirm libolm

# 2. pipx
#    Debian/Ubuntu sudo apt-get install -y pipx
#    Fedora        sudo dnf install -y pipx
#    Arch          sudo pacman -S --noconfirm python-pipx
#    macOS         brew install pipx

# 3. shelltrix
pipx install git+https://github.com/Nawal-alao/shelltrix.git
```

### Windows

No native build. Install inside [WSL2](https://learn.microsoft.com/windows/wsl/install)
(Ubuntu recommended) and run the commands above from your WSL terminal.

---

## Usage

```bash
shelltrix
```

On first launch, a login screen asks for your homeserver, user ID, and
password. Credentials are stored in `~/.config/shelltrix/` with `600`
permissions — subsequent launches go straight to the chat interface.

### From a local checkout

```bash
# Option A — alias
echo "alias shelltrix='$(pwd)/.venv/bin/shelltrix'" >> ~/.bashrc

# Option B — symlink (works in scripts)
ln -s "$(pwd)/.venv/bin/shelltrix" ~/.local/bin/shelltrix
```

---

## Shortcuts

| Key | Action |
|-----|--------|
| `Ctrl+P` | Command palette |
| `Ctrl+R` | Focus room list |
| `Ctrl+L` | Focus composer |
| `Ctrl+K` | Clear active timeline |
| `Ctrl+D` | Toggle sidebar |
| `Ctrl+Q` | Quit |
| `Enter` | Send message (in composer) |
| `↑` / `↓` + `Enter` | Navigate & open room |

---

## Command palette

Open with `Ctrl+P`. Type to search instantly through commands organized in
four sections:

| Section | Commands |
|---------|----------|
| **Navigation** | Focus rooms, focus composer, toggle sidebar |
| **Chat** | Clear screen, mark as read, join room |
| **Action** | Insert `/sendimg`, open last link |
| **System** | Sync status, switch theme, log out, quit |

Navigate with `↑`/`↓` or `Ctrl+P`/`Ctrl+N`, confirm with `Enter`, close
with `Esc`.

---

## Slash commands

Type `/` in the composer to trigger fuzzy autocompletion:

| Command | Description |
|---------|-------------|
| `/me <text>` | Send an action (italic emote) |
| `/react <emoji>` | React to the last message |
| `/join <#alias>` | Join a room by alias |
| `/sendimg <path>` | Send an image from disk (E2EE) |
| `/search <text>` | Search local message history |
| `/recovery` | Show / regenerate E2EE session key |
| `/theme` | Switch theme |
| `/quit [farewell]` | Leave the room |
| `/help` | Show command list |

`@` and `#` in the composer also trigger mention / room completion.

---

## Sidebar

A context panel on the right (`Ctrl+D`):

- **Room** — name, alias, topic, member counts, encryption state, your
  power level (`Admin (100)` / `Moderator (50)` / `User`).
- **Session** — sync state (colored indicator), last refresh age.

---

## Themes

Two built-in themes, switchable live with `/theme`:

| Theme | Accent | Description |
|-------|--------|-------------|
| **opencode** | `#e59e72` | Warm dark (default) |
| **matrix_green** | `#50fa7b` | Deep green |

Persisted in `~/.config/shelltrix/config.json`. All CSS colors come from
theme variables — add a new theme by appending an entry to
`src/shelltrix/themes.py`.

---

## Features

### Core

- Login + continuous sync loop
- Room list, live timeline, message sending
- Receiving & decrypting encrypted messages (E2EE)
- Device verification by emoji (SAS) with manual confirmation
- Refuse to send to unverified devices
- Accept/Decline dialog for room invitations
- Clean logout: server-side token revocation + local credential wipe

### Security

- Access token stored in the **system keyring**, never in plaintext
- E2EE store encrypted at rest (Fernet, key in keyring)
- **Session recovery key** (`/recovery`): shareable secret for E2EE
  history restoration; only a scrypt verifier lives on disk
- Encrypted store auto-decrypted on startup via keyring or recovery key

### Interface

- ASCII art splash screen with gradient animation
- Centered card login with styled errors
- Top status bar: room name, sync indicator, clock
- Room list sorted by unread, with badges
- Timeline with conversation grouping, time-gap separators, inline
  markdown, and truecolor half-block image previews
- Sidebar with room & session context

### Reliability

- **Automatic reconnection** with exponential backoff (1s → 30s)
- **Server history / scrollback**: older messages loaded on PageUp
- Local message cache (`~/.config/shelltrix/cache/`) for instant re-open
- Splash auto-advances after ~3s (skip with `Enter` / `Esc`)

---

## Roadmap

1. Inline images (Sixel / Kitty graphics protocol)
2. Desktop notifications (`notify-send`)
3. Unread indicators per room
4. Multi-account support

---

## License

[MIT](LICENSE)
