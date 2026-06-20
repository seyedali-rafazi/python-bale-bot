# 🤖 Bale Downloader Bot

A comprehensive Telegram/Bale bot for downloading content from various platforms and processing media files.

## 📋 Table of Contents
- [Features](#features)
- [Installation](#installation)
- [Configuration](#configuration)
- [Usage](#usage)
- [User Limits](#user-limits)
- [Technologies](#technologies)

---

## ✨ Features

### 📺 YouTube Downloader
- **Download Videos**: Download YouTube videos in multiple qualities (144p - 720p)
- **Download Audio (MP3)**: Extract audio from YouTube videos
  - Sends as playable audio file (under 50MB)
  - Also provides ZIP backup for compatibility
- **Search Features**:
  - Last 5 videos from a channel
  - Search within specific channels
  - Global YouTube search
  - Direct link download
- **Shared Cache**: Access previously downloaded videos instantly
- **Smart Delivery**: Choose between ZIP or direct video upload

### 🖼 Image Processing (NEW!)
- **📄 Create PDF from Images**: Combine up to 20 images into a single PDF
- **🔄 Convert Image Format**: Convert between PNG, JPG, JPEG, WEBP, BMP, GIF
- **📏 Resize Images**:
  - Percentage-based resizing (e.g., 50%)
  - Dimension-based resizing (e.g., 800x600)
- **✂️ Remove Background**: AI-powered background removal (requires optional rembg library)

### 📸 Instagram Downloader
- Download posts and reels with direct links
- Support for photos and videos

### 🎵 Music Download & Recognition
- **Search & Download**:
  - Search by track name
  - Search by album
  - Search by artist
  - Download Spotify playlists
- **Music Recognition**: Identify songs from audio/video files (Shazam-like)

### 📌 Pinterest
- Search and download images from Pinterest
- Batch download support

### 🎬 TikTok
- Download TikTok videos with links
- Search TikTok by topic
- Browse trending TikTok videos

### ✈️ Telegram Content
- Download single messages with links
- Get latest 20 messages from public channels

### 🐙 GitHub
- Download entire repositories as ZIP
- Search GitHub repositories
- Browse user repositories

### 🤖 AI Features
- **💬 Smart Assistant**: AI-powered chat assistant
- **🖼 OCR**: Extract text from images
- **🗣 Text-to-Speech**: Convert text to audio
- **🎨 Image Generation**: Generate images from text descriptions

### 🔍 Web Search & Scraping
- Search the web by topic
- Download web pages with direct links

### 🌤 Weather
- Get weather forecasts for any city

### 🔤 Translation
- Persian to English
- English to Persian

### ☁️ Cloud Storage
- Upload files to personal cloud storage
- Manage stored files
- Purchase additional storage space (5GB, 10GB, 20GB, 50GB)

### 🪪 User Management
- User profiles
- VIP subscription system
- Usage statistics tracking

---

## 🚀 Installation

### Prerequisites
- Python 3.10+
- PostgreSQL or SQLite
- FFmpeg (for video processing)

### Install Dependencies

```bash
# Core dependencies
pip install python-telegram-bot aiosqlite python-dotenv

# YouTube & Video processing
pip install yt-dlp

# Image processing (NEW - required)
pip install Pillow>=10.0.0

# Background removal (OPTIONAL - only if you want this feature)
pip install rembg[cpu]  # for CPU
# OR
pip install rembg[gpu]  # for NVIDIA/CUDA GPU

# Web scraping & automation
pip install playwright beautifulsoup4 requests

# AI features
pip install openai

# Music recognition
pip install shazamio

# Additional utilities
pip install aiohttp asyncio
```

### Setup Playwright (for web scraping)
```bash
playwright install chromium
```

---

## ⚙️ Configuration

Create a `.env` file in the root directory:

```env
# Bot Configuration
BALE_TOKEN=your_bot_token_here
BALE_URL=your_webhook_url
BALE_LISTENING_PORT=8080

# Channel Configuration
CHANNEL_ID=your_channel_id
CHANNEL_URL=your_channel_url

# Storage Channel (for caching files)
STORAGE_CHANNEL_ID=your_storage_channel_id

# Database
DATABASE_URL=your_database_url

# API Keys (optional, for specific features)
OPENAI_API_KEY=your_openai_key
SHAZAM_API_KEY=your_shazam_key

# Cloud Storage (optional)
S3_BUCKET=your_s3_bucket
S3_ACCESS_KEY=your_access_key
S3_SECRET_KEY=your_secret_key
```

---

## 📖 Usage

### Starting the Bot

```bash
python main.py
```

### User Commands

- `/start` - Start the bot and show main menu
- `/tr <lang_pair> <text>` - Quick translation (e.g., `/tr fa:en سلام`)
- `/weather <city>` - Get weather forecast

### Admin Commands

- `/stats` - View bot statistics
- `/setvip <user_id> <status>` - Set VIP status (0 or 1)
- `/setexpire <user_id> <date>` - Set VIP expiration date
- `/userinfo <user_id>` - Get user information
- `/messageuser <user_id> <message>` - Send message to user
- `/resetlimits <user_id>` - Reset user's daily limits
- `/limit_yt <on/off>` - Toggle YouTube download limits
- `/resetuser <user_id>` - Reset user data
- `/addvipall <days>` - Add VIP days to all users
- `/addcloud <user_id> <mb>` - Add cloud storage to user
- `/give5gbvips` - Give 5GB cloud storage to all VIP users
- `/fixytcache` - Fix YouTube cache metadata
- `/cleanytcache` - Clean incomplete YouTube cache entries
- `/channelblacklist <add/remove/list> [channel]` - Manage blocked channels
- `/blockword <add/remove/list> [word]` - Manage blocked search terms
- `/monitor` - Get system monitoring report

---

## 👥 User Limits

### Free Users (Daily Limits)
- YouTube Downloads: **1 video/day** (upload to Bale only)
- Music Downloads: 6 tracks/day
- Pinterest Searches: 10 searches/day
- TikTok Downloads: 5 videos/day
- GitHub Downloads: 2 repos/day
- AI Chat: 2 requests/day
- Web Search: 1 search/day
- Telegram Downloads: 1 message/day
- YouTube Archive Search: 2 searches/day

### VIP Users (Daily Limits)
- YouTube Downloads: **20 videos/day**
- Music Downloads: 20 tracks/day
- Pinterest Searches: 40 searches/day
- TikTok Downloads: 30 videos/day
- GitHub Downloads: 20 repos/day
- AI Chat: 20 requests/day
- Web Search: 30 searches/day
- Telegram Downloads: 10 messages/day
- YouTube Archive Search: 20 searches/day
- **Bonus**: Additional cloud storage options

---

## 🛠 Technologies

### Core Framework
- **python-telegram-bot**: Telegram Bot API wrapper
- **asyncio**: Asynchronous programming
- **aiosqlite**: Async SQLite database

### Media Processing
- **yt-dlp**: YouTube video/audio downloading
- **FFmpeg**: Video/audio processing
- **Pillow (PIL)**: Image manipulation
- **rembg**: AI-powered background removal

### Web Automation
- **Playwright**: Browser automation for web scraping
- **BeautifulSoup4**: HTML parsing
- **aiohttp**: Async HTTP client

### AI & Recognition
- **OpenAI API**: AI chat and image generation
- **Shazamio**: Music recognition

### Storage & Database
- **SQLite/PostgreSQL**: Data persistence
- **S3 Compatible Storage**: Cloud file storage

---

## 📁 Project Structure

```
.
├── main.py                 # Bot entry point
├── core/                   # Core functionality
│   ├── constants.py        # Button labels and constants
│   ├── keyboards.py        # Keyboard layouts
│   ├── limits.py          # User limits configuration
│   ├── state_manager.py   # User state management
│   ├── admin.py           # Admin commands
│   └── database/          # Database operations
├── handlers/              # Message and callback handlers
│   ├── commands.py        # Command handlers
│   ├── menus/            # Menu handlers
│   └── states/           # State handlers for each feature
├── services/             # External service integrations
│   ├── youtube.py        # YouTube download service
│   ├── instagram.py      # Instagram service
│   ├── music.py          # Music download service
│   ├── ai.py             # AI services
│   ├── translator.py     # Translation service
│   └── ...
└── README.md             # This file
```

---

## 🔒 Security & Privacy

- User data is stored securely in the database
- File downloads are temporary and cleaned up automatically
- VIP subscriptions are time-limited
- Admin commands require authentication
- Blocked channels and keywords prevent abuse

---

## 📝 License

This project is proprietary software. All rights reserved.

---

## 🤝 Support

For support and questions, use the bot's support button: **👨‍💻 پشتیبانی و مشکلات**

---

## 🎯 Recent Updates

### Latest Features (v1.0)
- ✅ **Image Processing Menu**: PDF creation, format conversion, resizing, background removal
- ✅ **Enhanced YouTube Audio**: Now sends both audio file and ZIP
- ✅ **Free User YouTube Access**: 1 download per day for free users
- ✅ **Improved User Experience**: Better error handling and progress updates

---

## 🚧 Roadmap

- [ ] Video editing features
- [ ] More AI capabilities
- [ ] Multi-language support
- [ ] Advanced analytics dashboard
- [ ] Batch download improvements

---

**Made with ❤️ for Bale Messenger**