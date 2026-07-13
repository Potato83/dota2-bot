# Dota 2 Safe Bot Loop

Automated script for finding matches, accepting queues, and locking in heroes in Dota 2. Uses pure image recognition (OpenCV) and simulated inputs. Farming ticket events by launching matchmaking against bots.

## ⚠️ Disclaimer
**FUCK DOTA, PLAY DEADLOCK**: This script was created to avoid playing Dota. It was made using AI.

**This tool emulates user input. Using automation tools in Dota 2 violates the Steam Terms of Service. It can potentially lead to an account ban or a VAC ban.** This repository is for educational purposes and proof-of-concept only. Use entirely at your own risk.

## 🖥️ System Requirements

### General In-Game Settings:
- **Display Mode:** Borderless Windowed (Required for accurate screen grabbing).
- **UI Scaling:** Ensure your OS display scaling is set to **100%**.
- **UI Language**: English, otherwise you will have to take screenshots of the buttons yourself.

### OS Specifics:
- **Windows:** Fully supported out of the box.
- **Linux:** X11 session is **required**. Wayland is unsupported, but also can be used.
  - Install dependency: 
  * `sudo apt install xdotool` (Debian/Ubuntu); 
  * `sudo dnf install xdotool` (Fedora);
  * `sudo pacman -S install xdotool` (Arch);

## 📁 Asset Setup

The bot relies on Computer Vision to locate buttons. You must populate the `btns/` folder with cropped `.png` screenshots of your exact in-game buttons(already in project folder):
- `play_btn.png`
- `find_btn.png`
- `accept_btn.png`
- `lock_btn.png`
- `continue_btn_red.png`
- `continue_btn_green.png`

## 🚀 Quick Start
**On all systems:**
You need Python 3.10 or newer

**On Windows:**
Simply run `start.bat`. It will create a virtual environment, install dependencies, and launch the bot.

**On Linux:**
```bash
chmod +x start.sh
./start.sh
```

**Passing Heroes via CLI:**
Instead of typing heroes interactively, you can pass them as arguments:

```bash
./start.sh abaddon, pudge, lina
```

## Project structure

```
dota_safe_bot/
├── dota_safe_bot.py      # Main bot script
├── start.sh              # Linux launcher
├── start.bat             # Windows launcher
├── requirements.txt      # Python dependencies
├── .gitignore            # Git exclusions
└── btns/                 # Template screenshots (user-created)
    ├── .gitkeep
    ├── play_btn.png
    ├── find_btn.png
    ├── accept_btn.png
    ├── lock_btn.png
    ├── continue_btn_red.png
    └── continue_btn_green.png
```

## 🛑 Emergency Stop

The script handles `Ctrl+C` for a graceful shutdown. If your mouse is stuck while dragging (Windows), aggressively move your mouse cursor to the top-left corner of your physical screen to trigger the PyAutoGUI/PyDirectInput failsafe mechanism.

## Presets

Auto-farm event tickets:
```
io, rubick, oracle, doom, wraith, jakiro, sven, abaddon, kotl, chaos, muerta
```

Auto-farm Smelt tokens:
```
muerta, muerta, wraith, wraith, sven, sven, kotl, oracle
```
