# nerve

A premium Matrix TUI client, written in Python, designed as a solid
daily replacement for gomuks terminal / iamb.

**Stack** : [`matrix-nio`](https://github.com/matrix-nio/matrix-nio) (Matrix SDK, E2EE via libolm) + [`Textual`](https://textual.textualize.io/) (modern TUI framework).

## Why this instead of gomuks terminal

- `matrix-nio` does *not* do cross-signing — only manual/emoji verification, device by device. This is the exact bug you hit with `/cs fetch` on gomuks (`illegal base64 data`) and it does not exist here: no broken "recovery key" flow.
- `Textual` has a real styling engine (CSS-like, see `app.tcss`) — the rounded borders in the lazygit style are already in place, and everything is customizable without touching the Python code.
- The code is yours: every behavior (how a room displays, what happens on invitation, etc.) lives in this repo, not hidden in an experimental Go binary.

## Installation

Nerve requires **Linux or macOS** with **Python ≥ 3.10**. The installer
checks for these, installs the `libolm` encryption dependency and `pipx`,
then installs Nerve:

```bash
curl -fsSL https://raw.githubusercontent.com/Nawal-alao/nerve/main/install.sh | sh
```

Then verify:

```bash
nerve --version
```

### Windows (via WSL2)

There is **no native Windows build**. On Windows, install Nerve inside
[WSL2](https://learn.microsoft.com/windows/wsl/install) (Ubuntu
recommended), then run the install command above from your WSL terminal.

### Manual installation

Prefer not to `curl | sh`? Do the equivalent steps yourself:

```bash
# 1. Install the libolm encryption library (one of, depending on your OS)
#    macOS:  brew install libolm
#    Debian/Ubuntu:  sudo apt-get install -y libolm-dev
#    Fedora:  sudo dnf install -y libolm-devel
#    Arch:    sudo pacman -S --noconfirm libolm

# 2. Install pipx (or use `uv tool install` if you already use uv)
#    Debian 11+/Ubuntu 23.04+ block global pip (PEP 668), so use the package manager:
#    Debian/Ubuntu:  sudo apt-get install -y pipx
#    Fedora:         sudo dnf install -y pipx
#    Arch:           sudo pacman -S --noconfirm python-pipx
#    macOS:          brew install pipx
#    (or, legacy:    python3 -m pip install --user pipx && python3 -m pipx ensurepath)

# 3. Install Nerve
pipx install git+https://github.com/Nawal-alao/nerve.git

# 4. Verify
nerve --version
```

## Run

```bash
nerve
```

On first launch, a login screen asks for your homeserver, user ID and password. An `access_token` is then saved in `~/.config/nerve/credentials.json` (permissions `600`) — later launches go straight to the chat interface.

### Running from the repo (venv)

Installed via `pipx`/`uv` (the install script above), `nerve` is already on
your `PATH`. When running from a local checkout, expose it globally instead:

```bash
echo "alias nerve='/path/to/nerve/.venv/bin/nerve'" >> ~/.bashrc
source ~/.bashrc
```

or symlink the wrapper into a directory already on your `PATH` (works in
scripts too, not just interactive shells):

```bash
ln -s /path/to/nerve/.venv/bin/nerve ~/.local/bin/nerve
```

Each launch starts with a minimal splash banner: a fixed `NERVE` ASCII block
art (hand-drawn, no `figlet`/`pyfiglet` dependency) revealed column-by-column
with a theme-driven gradient (`$muted` → `$text`), a discreet typing tagline
(`secure · private · minimal`, no cursor), then auto-advances to login or chat
after ~3s (`enter` / `esc` to skip anytime). Small terminals adapt the layout
(compact hint; the logo is hidden below 44 columns).

## Shortcuts (current state)

- `Ctrl+P` : command palette (see dedicated section below)
- `Ctrl+R` : focus room list
- `Ctrl+L` : focus the composer
- `Ctrl+K` : clear the active room timeline
- `Ctrl+D` : show or hide the sidebar (context panel, on by default)
- `Enter` in the composer : send the message
- `↑`/`↓` in the room list then `Enter` : open a room
- `/theme` : toggle theme (also `theme` command in the palette, under System)

## Command palette (`Ctrl+P`)

opencode-style: instant search over title/description, flat design,
**non-selectable section headers** (`Suggested` / `Chat` / `Action` /
`System`), **discreet category badge** on the right (`[Navigation]` /
`[Chat]` / `[Action]` / `[System]`), keyboard shortcut displayed on the
right of the row, and an empty state if there is no result. Navigate with
`↑`/`↓` (or `Ctrl+P`/`Ctrl+N`), run with `Enter`, close with `Esc`.

Available commands:

- Navigation : focus rooms / focus composer (suggested), toggle sidebar (`Ctrl+D`)
- Chat : clear screen (`Ctrl+K`), mark as read, join a room (`#alias` prompt in a dialog)
- Action : insert `/sendimg`, open the room's last link
- System : sync status, switch theme, log out (back to login), quit nerve (`Ctrl+Q`)

## Sidebar (context panel)

A flat `30` column on the right of the chat, on by default, toggled with
`Ctrl+D` (also in the palette under Navigation). It shows:

- **Room** : name and canonical alias, topic (truncated if long), member
  counts (`12 joined · 2 invited` via the room summary), encryption state
  (bold `E2EE enabled` when the room is encrypted) and your power level
  (`Admin (100)` / `Moderator (50)` / `User`).
- **Session** : sync state (colored dot + label, `off-line` in red when
  disconnected), truncated sync token (`next_batch`) and the age of the
  last refresh (`Refresh 3s ago`).

## Themes

Two native Textual themes, switching live with `/theme` (or the `theme`
command in the palette / `Ctrl+P` → System):

- **opencode** — the default, warm dark tones (accent `#e59e72`).
- **matrix_green** — deep green (accent `#50fa7b`).

The choice is persisted in `~/.config/nerve/config.json` and re-applied at
every launch (login, chat and palette all follow the active theme). All CSS
colors in `app.tcss` come from theme variables, so adding a new theme only
means appending an entry to `src/nerve/themes.py`.

## Premium interface

- Centered card login screen (branding, button, styled errors)
- Top status bar: active room, sync indicator (offline / syncing… / online) and clock
- Room list sorted (unread first), with unread badge and highlighted active room
- Timeline: **conversationally grouped** — consecutive messages from the same sender collapse into a block with a single `› Vous` / `‹ Name` indicator; a dimmed `HH:MM ────` separator appears after ~5 min of silence. **Server history / scrollback**: opening a room loads the most recent messages from the server, and scrolling to the top (`PageUp`) fetches older batches. `Ctrl+K` clears the active room timeline. Inline markdown (bold, italic, code, strikethrough) and safe inline image previews (truecolor half-blocks — never raw escape sequences on stdout)
- Slash commands in the composer: `/me <text>` (italic action line), `/react <emoji>` (react to the last message), `/join <#alias>`, `/sendimg <path>` (send an image from disk, encrypted like E2EE messages), `/recovery` (show or regenerate the E2EE session recovery key), `/theme`, `/quit [goodbye]`, `/help`. Type `/` to open a **fuzzy-search autocompletion** (fzf-like): navigate with ↑/↓, Tab or Enter completes, Esc closes. Type `@` (room members) or `#` (rooms) for the same fuzzy **mention completion**, also confirmed with Tab/Enter (your own user is excluded). An unknown or malformed command shows an error and is never sent as a message.
- Palette fully driven by `app.tcss` (design tokens at the top of the file; theme-driven values).

## What already works

- Login + continuous sync loop
- **Automatic reconnection with exponential backoff** (1s → 30s): on a network outage the app re-syncs on its own instead of dropping to "off-line" forever. The header shows `syncing…` / `online` / `off-line` / `reconnecting…`
- Room list, live timeline, message sending
- Receiving/decrypting encrypted messages (E2EE)
- Device verification by emoji (SAS) **with human confirmation**: the emojis are displayed on screen and the device is only validated if you compare them yourself (never auto-confirmed).
- Refuse to send to unverified devices: in an encrypted room, if a contact hasn't validated their device, sending is blocked and you're warned (no potentially compromised recipient).
- **Human confirmation of invitations**: a room is never joined automatically — a dialog requires Accept/Decline.
- Access token stored in the **system keyring**, never in plaintext in `credentials.json`.
- **E2EE store encrypted at rest**: olm/megolm session keys are Fernet-encrypted (key in the keyring) as soon as the app closes.
- **Session recovery key** (`/recovery`): the store key is exposed as a shareable secret so the session (E2EE history) can be restored on a new machine or after the keyring is wiped. Only a scrypt verifier of the key is stored on disk — never the key itself. On startup, if the keyring key is missing, nerve asks for the recovery key instead of failing.
- **Command palette** (`Ctrl+P`) and **clean logout**: the token is revoked server-side, then local credentials and the store are deleted.

## Roadmap to "real" premium

In the order I'd recommend tackling it:

1. **Inline markdown/images rendering** — Textual supports rich rendering, so basic markdown (bold, code) is nearly free in `RichLog`. Inline images would need Sixel/Kitty graphics protocol rendering (your Kitty terminal already supports it).
2. **Desktop notifications** — via `notify-send` or a lib like `plyer`, triggered from `_handle_message` when the room isn't active.
3. **Unread indicators** per room in the list.
4. **Username/room completion** in the composer.
5. **Multi-account** — `NerveClient` is already decoupled from the UI, so running several instances in parallel is possible.

## Security — good to know

- The access token and store key live in the system keyring. On systems without a keyring daemon (e.g. headless server), keyring falls back to one of the weaker backends: configure a real keyring (Secret Service / keychain) for actual protection.
- If the store is corrupted (e.g. after a crash during end-of-session encryption), delete `~/.config/nerve/store`: devices stay valid, only non-re-synced history is lost.
- To restore a session anywhere, run `/recovery` once and save the shown key offline. On a new machine or after the keyring is wiped, nerve will detect the encrypted store and ask for that key before loading the chat.