# HexIron Music Bot 🎵

A production-ready Telegram music bot with modular source architecture, voice chat playback, interactive control panel, user uploads, favorites, and admin management.

## Features

- 🎵 **YouTube Search & Playback** — Search YouTube and play audio in voice chats
- 🔗 **YouTube URL Support** — Paste YouTube or YouTube Shorts URLs directly
- 🎵 **TikTok Support** — Play audio from TikTok URLs (when extraction works)
- 🔗 **Direct URL Support** — Play audio from direct media URLs (MP3, M4A, WAV, etc.)
- 📤 **Telegram Uploads** — Send audio files directly to play them
- 🎛 **Interactive Control Panel** — Inline keyboard with play/pause/skip/stop/volume/loop/shuffle
- 📜 **Queue System** — Add, view, remove, shuffle, and clear the queue
- ❤️ **Favorites** — Save and manage personal favorite songs
- 🔀 **Shuffle & Loop** — Shuffle queue, loop current song, or loop entire queue
- 🔊 **Volume Control** — Per-chat volume adjustment
- 📊 **Admin Panel** — Statistics, user/group management, storage monitoring, broadcast
- 🔒 **Per-Chat Settings** — Auto-play, default volume, loop mode, upload/search permissions
- 🤖 **AI Integration Ready** — Configurable AI provider for natural-language music search
- 🐳 **Docker & Liara Ready** — Production deployment out of the box

## Architecture

```
Search / URL / Telegram Upload
        ↓
  Source Detection (auto-detect YouTube, TikTok, URL, search)
        ↓
  Music Provider (YouTube / TikTok / Generic / Telegram upload)
        ↓
  Unified MusicItem
        ↓
  Queue (SQLite per-chat)
        ↓
  Player (PyTgCalls → Voice Chat)
```

```
┌──────────────────────────────────────────────────────┐
│                      main.py                          │
│  ┌──────────┐  ┌──────────┐  ┌────────────────────┐  │
│  │   Bot     │  │ Userbot  │  │  PyTgCalls         │  │
│  │ (Pyrogram)│  │(Pyrogram)│  │  (Voice Chat)      │  │
│  └─────┬────┘  └─────┬────┘  └───────┬────────────┘  │
│        │              │               │                │
│  ┌─────┴──────────────┴───────────────┴─────────────┐ │
│  │              handlers/                            │ │
│  │  admin.py  player.py  control_panel.py  search.py│ │
│  └───────────────────┬──────────────────────────────┘ │
│  ┌───────────────────┴──────────────────────────────┐ │
│  │              music/sources/                       │ │
│  │  router.py  base.py  item.py                     │ │
│  │  youtube.py  tiktok.py  generic.py               │ │
│  └───────────────────┬──────────────────────────────┘ │
│  ┌───────────────────┴──────────────────────────────┐ │
│  │              services/                            │ │
│  │  player_state.py  permissions.py  favorites.py   │ │
│  │  storage.py  ai_service.py                       │ │
│  └───────────────────┬──────────────────────────────┘ │
│  ┌───────────────────┴──────────────────────────────┐ │
│  │              database.py (SQLite)                 │ │
│  │  groups  users  queue  favorites                  │ │
│  │  chat_settings  statistics                        │ │
│  └──────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────┘
```

## Prerequisites

- Python 3.10+
- FFmpeg installed on the system
- Telegram Bot Token (from @BotFather)
- Telegram API credentials (from https://my.telegram.org)
- A separate Telegram account for the userbot session

## Installation

### Local Development

```bash
# 1. Clone the repository
git clone https://github.com/hesiterndo-ship-it/hexiron-music.git
cd hexiron-music

# 2. Create a virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure environment
cp .env.example .env
# Edit .env with your actual values

# 5. Generate userbot session (one-time)
python generate_session.py

# 6. Run the bot
python main.py
```

### Docker Deployment

```bash
# Build and run
docker build -t hexiron-music .
docker run -d \
  --name hexiron-music \
  --env-file .env \
  -v hexiron-data:/data \
  hexiron-music
```

### Liara Deployment

The project includes `liara.json` for Liara PaaS deployment:

```bash
# Install Liara CLI
npm install -g @liara/cli

# Deploy
liara deploy
```

## Environment Variables

### Required

| Variable | Description |
|----------|-------------|
| `BOT_TOKEN` | Telegram bot token from @BotFather |
| `API_ID` | Telegram API ID from my.telegram.org |
| `API_HASH` | Telegram API hash from my.telegram.org |
| `OWNER_ID` | Your Telegram user ID (numeric) |
| `STRING_SESSION` | Userbot session string (run `generate_session.py`) |

### Optional — Provider Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `SOCKS5_PROXY_URL` | | SOCKS5 proxy for Telegram connection and downloads |
| `YTDLP_COOKIES_FILE` | | Path to yt-dlp cookies file for age-restricted content |
| `GENERIC_MAX_SIZE_BYTES` | `209715200` | Max download size for direct URLs (200 MB) |
| `GENERIC_DOWNLOAD_TIMEOUT` | `120` | Download timeout in seconds |

### Optional — Player & Storage

| Variable | Default | Description |
|----------|---------|-------------|
| `DEFAULT_VOLUME` | `100` | Default playback volume (0-200) |
| `MAX_QUEUE_SIZE` | `200` | Maximum songs in queue |
| `MAX_UPLOAD_SIZE_MB` | `50` | Maximum upload file size |
| `DATA_DIR` | `/data` | Main data directory |
| `DATABASE_URL` | `/data/hexiron.db` | SQLite database path |
| `LOG_LEVEL` | `INFO` | Logging level |

### Optional — Licensing & AI

| Variable | Default | Description |
|----------|---------|-------------|
| `CENTRAL_API_URL` | `http://localhost:8080` | Licensing API URL |
| `CENTRAL_API_KEY` | | Licensing API key |
| `AI_PROVIDER` | | `openai` or `gemini` |
| `AI_API_KEY` | | AI provider API key |

See `.env.example` for the complete list.

## Music Sources

### YouTube (Primary)

- Search by song name: `/play The Weeknd Blinding Lights`
- Direct URL: `/play https://www.youtube.com/watch?v=dQw4w9WgXcQ`
- YouTube Shorts: supported
- Audio extraction via yt-dlp + FFmpeg
- Results are cached in `downloads/youtube/`

### TikTok

- Send a TikTok URL to play it
- Extraction via yt-dlp
- **Limitation**: TikTok extraction may fail due to platform restrictions, regional locks, or API changes. The bot will return a clean error message if extraction fails.

### Direct Media URLs

- Send a direct URL to an audio file (MP3, M4A, WAV, OGG, FLAC, etc.)
- SSRF protection blocks private/loopback addresses
- File size and timeout limits enforced

### Telegram Uploads

- Send an audio file directly to the bot in a group
- Supported: MP3, M4A, WAV, OGG/OPUS, FLAC, WMA
- Metadata extracted from Telegram audio tags

## Bot Commands

### User Commands

| Command | Description |
|---------|-------------|
| `/start` | Welcome message (private chat) |
| `/play <name or URL>` | Search and play a song, or play a URL |
| `/pause` | Pause playback |
| `/resume` | Resume playback |
| `/skip` | Skip to next song |
| `/stop` | Stop and clear queue |
| `/queue` | View the queue |
| `/previous` (or `/prev`, `/back`) | Go back to the previously played track |
| `/panel` | Open interactive control panel |
| `/search <query>` | Search for music (shows selectable results) |
| `/aiplay <feeling/style>` | AI-assisted search (requires AI provider configured) |
| `/fav` | View your favorites |

### Admin Commands

| Command | Description |
|---------|-------------|
| `/admin` | Open admin panel |
| `/broadcast <msg>` | Send message to all groups (owner only) |

### Control Panel

Use `/panel` to open the interactive keyboard:
- ⏮ Previous, ▶️ Play/Resume, ⏭ Next, ⏹ Stop
- 📜 Queue, 🎧 Now Playing, 📤 Upload hint, ❤️ Save to Favorites
- 🔁 Loop (Off / Current Song / Queue), 🔀 Shuffle, 🤖 AI suggestion hint
- 🔊 Volume control (Mute / - / + / Max)
- 🔄 Refresh, ❌ Close

"Previous" replays the last track from this session's history and puts the
song that was playing back at the front of the queue, so a later "Next"
returns exactly where you left off.

See `DEPLOY-LIARA-VPS.md` for a full walkthrough of deploying this bot
together with `hexiron-sales` (subscription/licensing) on a Liara VPS,
and wiring up Liara AI.

## Deployment

### VPS

1. Install Python 3.10+ and FFmpeg
2. Clone the repository
3. Create and configure `.env`
4. Run with `python main.py` or use a process manager (systemd, supervisor)

### Liara

1. Push code to GitHub
2. Connect repository in Liara dashboard
3. Set environment variables in Liara console
4. The persistent disk (`/data`) stores database and downloads

### Persistent Storage

The following directories need persistence across restarts:
- `/data` — main data directory (contains everything below)
- `/data/hexiron.db` — SQLite database
- `/data/downloads/` — cached music files
- `/data/uploads/` — user-uploaded audio files

## Troubleshooting

### Bot doesn't join voice chat
- Ensure the userbot account is a member of the group
- Ensure a voice chat is already active in the group
- Check that UDP outbound traffic is not blocked

### Songs don't play
- Verify FFmpeg is installed: `ffmpeg -version`
- Check bot logs for errors
- Ensure the userbot has voice chat permissions

### YouTube search fails
- Ensure yt-dlp is installed: `pip install yt-dlp`
- Check network connectivity
- For age-restricted content, configure `YTDLP_COOKIES_FILE`

### TikTok extraction fails
- TikTok frequently changes their platform, which can break extraction
- This is a known limitation — YouTube and Telegram uploads will continue working

## Testing

```bash
# Run source detection tests
python -m pytest tests/ -v
```

## License

This project is for educational purposes.