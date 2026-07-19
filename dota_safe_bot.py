"""
Dota 2 Safe Bot Loop — Automated match finding and hero picking.
Uses computer vision (OpenCV) and virtual inputs to automate the Dota 2 pre-game loop.
"""

import sys
import os
import time
import signal
import logging
import subprocess
import threading
from enum import Enum, auto
from pathlib import Path
from typing import Union, Optional, Tuple, Dict

import cv2
import numpy as np

# Conditional imports for Windows OS
IS_WINDOWS = sys.platform == "win32"
if IS_WINDOWS:
    try:
        import pydirectinput
        import pygetwindow as gw
        pydirectinput.FAILSAFE = True
    except ImportError:
        pydirectinput = None
        gw = None
    try:
        from mss import MSS
    except ImportError:
        MSS = None
else:
    gw = None
    pydirectinput = None
    if not os.environ.get("WAYLAND_DISPLAY"):
        try:
            from mss import MSS
        except ImportError:
            MSS = None
    else:
        MSS = None

# --- SAFE ENVIRONMENT PARSING ---
def _get_env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, str(default)))
    except ValueError:
        return default

def _get_env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, str(default)))
    except ValueError:
        return default

CONFIDENCE_LEVEL = _get_env_float("BOT_CONFIDENCE", 0.8)
MATCH_END_TIMEOUT = _get_env_float("BOT_MATCH_TIMEOUT", 7200.0)
TYPING_DELAY = _get_env_int("BOT_TYPING_DELAY", 120)

BTNS_DIR = Path(__file__).parent.resolve() / "btns"
IMG_PLAY = "play_btn.png"
IMG_FIND = "find_btn.png"
IMG_ACCEPT = "accept_btn.png"
IMG_LOCK = "lock_btn.png"
IMG_OK = "ok_btn.png"
IMG_CONTINUE_LIST = ["continue_btn_red.png", "continue_btn_green.png"]

# Global logger initialization
logger = logging.getLogger(__name__)

# --- STATE MACHINE ---
class State(Enum):
    MENU = auto()
    PICK = auto()
    MATCH = auto()

# --- GRACEFUL SHUTDOWN HANDLER ---
class Killer:
    def __init__(self):
        self.kill_now = False
        if threading.current_thread() is threading.main_thread():
            try:
                signal.signal(signal.SIGINT, self._handler)
                signal.signal(signal.SIGTERM, self._handler)
            except ValueError:
                pass

    def _handler(self, signum, frame):
        logger.info("Shutdown signal received. Exiting gracefully...")
        self.kill_now = True

    def sleep(self, seconds: float):
        """Interruptible sleep"""
        deadline = time.time() + seconds
        while time.time() < deadline and not self.kill_now:
            time.sleep(0.1)

# --- TEMPLATE CACHE ---
class TemplateCache:
    def __init__(self, directory: Path):
        self._cache: Dict[str, np.ndarray] = {}
        self._dir = directory

    def load(self, *names: str) -> None:
        for name in names:
            path = self._dir / name
            if not path.exists():
                logger.error("Template missing: %s", path)
                continue
            img = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
            if img is None:
                logger.error("Cannot decode template: %s", path)
                continue
            self._cache[name] = img
            logger.debug("Loaded template: %s", name)

    def get(self, name: str) -> Optional[np.ndarray]:
        return self._cache.get(name)

# --- WINDOW UTILS ---
def get_dota_window() -> Union['gw.Win32Window', str, None]:
    if IS_WINDOWS:
        if gw is None:
            return None
        try:
            windows = gw.getWindowsWithTitle("Dota 2")
            for w in windows:
                if w.title and w.title.startswith("Dota 2"):
                    return w
        except Exception as e:
            logger.debug("Failed to get windows on Windows: %s", e)
        return None
    else:
        candidates = []
        for args in (
            ["search", "--onlyvisible", "--class", "dota2"],
            ["search", "--class", "dota2"],
            ["search", "--onlyvisible", "--name", "Dota 2"],
        ):
            try:
                out = subprocess.check_output(["xdotool", *args], text=True, timeout=5)
                for line in out.strip().splitlines():
                    if line.strip().isdigit():
                        candidates.append(line.strip())
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
                continue

        seen = set()
        for wid in candidates:
            if wid in seen:
                continue
            seen.add(wid)
            try:
                geo_out = subprocess.check_output(
                    ["xdotool", "getwindowgeometry", "--shell", wid],
                    text=True, timeout=3,
                )
                geo = {}
                for line in geo_out.strip().splitlines():
                    if "=" in line:
                        k, v = line.split("=", 1)
                        try:
                            geo[k] = int(v)
                        except ValueError:
                            continue

                w, h = geo.get("WIDTH", 0), geo.get("HEIGHT", 0)
                if w > 100 and h > 100:
                    name = subprocess.check_output(["xdotool", "getwindowname", wid], text=True, timeout=3).strip()
                    if "dota" in name.lower():
                        return wid
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
                continue
        return None

def get_window_rect(window_id) -> Optional[Tuple[int, int, int, int]]:
    if window_id is None:
        return None

    if IS_WINDOWS:
        try:
            if window_id.isMinimized:
                return None
            w, h = window_id.width, window_id.height
            if w <= 0 or h <= 0:
                return None
            return window_id.left, window_id.top, w, h
        except Exception:
            return None
    else:
        try:
            out = subprocess.check_output(
                ["xdotool", "getwindowgeometry", "--shell", str(window_id)],
                text=True, timeout=5
            )
            geo = {}
            for line in out.strip().splitlines():
                if "=" in line:
                    k, v = line.split("=", 1)
                    try:
                        geo[k] = int(v)
                    except ValueError:
                        continue
            w, h = geo.get("WIDTH", 0), geo.get("HEIGHT", 0)
            if w <= 0 or h <= 0:
                return None
            return geo.get("X", 0), geo.get("Y", 0), w, h
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
            return None

def activate_window(window_id) -> bool:
    if window_id is None:
        return False
    if IS_WINDOWS:
        try:
            if not window_id.isActive:
                window_id.activate()
                time.sleep(0.2)
            return True
        except Exception as e:
            logger.debug("Failed to activate window: %s", e)
            return False
    else:
        try:
            subprocess.run(["xdotool", "windowactivate", str(window_id)], check=True, capture_output=True, timeout=5)
            time.sleep(0.2)
            return True
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError) as e:
            logger.debug("xdotool windowactivate failed: %s", e)
            return False

# --- INPUT AUTOMATION ---
def dota_click(window_id, x: int, y: int):
    """Executes a click at absolute coordinates (x, y)."""
    if not activate_window(window_id):
        return

    if IS_WINDOWS:
        if pydirectinput:
            try:
                pydirectinput.moveTo(x, y)
                time.sleep(0.05)
                pydirectinput.click()
            except Exception as e:
                logger.error("Windows click automation failed: %s", e)
    else:
        rect = get_window_rect(window_id)
        if rect is None:
            return
        wx, wy, _, _ = rect
        rel_x = x - wx
        rel_y = y - wy
        try:
            subprocess.run(
                [
                    "xdotool",
                    "mousemove", "--window", str(window_id), str(rel_x), str(rel_y),
                    "windowfocus", str(window_id),
                    "click", "1",
                ],
                check=True, capture_output=True, timeout=5,
                )
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError) as e:
            logger.error("Click failed: %s", e)

def dota_send_key(window_id, key_name: str):
    if not activate_window(window_id):
        return
    if IS_WINDOWS:
        if pydirectinput:
            try:
                pydirectinput.press(key_name)
            except Exception as e:
                logger.error("Windows keypress failed: %s", e)
    else:
        try:
            subprocess.run(
                ["xdotool", "key", "--window", str(window_id), key_name],
                check=True, capture_output=True, timeout=5
            )
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError) as e:
            logger.error("Keypress failed: %s", e)

def dota_type_text(window_id, text: str):
    if not activate_window(window_id):
        return

    safe_text = text.lower()
    if IS_WINDOWS:
        if pydirectinput:
            try:
                pydirectinput.press("esc")
                time.sleep(0.2)
                pydirectinput.typewrite(safe_text, interval=0.1)
            except Exception as e:
                logger.error("Windows typing failed: %s", e)
    else:
        dota_send_key(window_id, "Escape")
        time.sleep(0.2)
        try:
            subprocess.run(
                ["xdotool", "type", "--window", str(window_id), "--delay", str(TYPING_DELAY), safe_text],
                check=True, capture_output=True, timeout=5,
            )
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError) as e:
            logger.error("Typing failed: %s", e)

# --- COMPUTER VISION ---
def find_template(screen_gray: np.ndarray, template: np.ndarray) -> Optional[Tuple[int, int]]:
    """Returns the (x, y) coordinates of the template's center relative to the screen screenshot."""
    if template.shape[0] > screen_gray.shape[0] or template.shape[1] > screen_gray.shape[1]:
        return None
    try:
        res = cv2.matchTemplate(screen_gray, template, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(res)
        if max_val >= CONFIDENCE_LEVEL:
            h, w = template.shape[:2]
            return max_loc[0] + w // 2, max_loc[1] + h // 2
    except cv2.error as e:
        logger.debug("OpenCV matching error: %s", e)
    return None

def capture_window_gray(sct: Optional['MSS'], rect: Optional[Tuple[int, int, int, int]]) -> Optional[np.ndarray]:
    """Captures the designated rectangle or screen and converts to Grayscale (Supports X11 & Wayland)."""
    if IS_WINDOWS:
        if sct is None or rect is None:
            return None
        x, y, w, h = rect
        monitor = {"left": x, "top": y, "width": w, "height": h}
        try:
            raw = np.array(sct.grab(monitor))
            return cv2.cvtColor(raw, cv2.COLOR_BGRA2GRAY)
        except Exception as e:
            logger.error("Screenshot failed on Windows: %s", e)
            return None
    else:
        # Linux Path: Check for Wayland Session
        if os.environ.get("WAYLAND_DISPLAY"):
            tmp_path = "/tmp/dota_bot_screen.png"
            captured = False
            # Fallback chain for Wayland capture utilities
            for cmd in [["spectacle", "-b", "-n", "-o", tmp_path], ["grim", tmp_path], ["gnome-screenshot", "-f", tmp_path]]:
                try:
                    res = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5)
                    if res.returncode == 0 and os.path.exists(tmp_path):
                        captured = True
                        break
                except Exception:
                    continue

            if captured:
                screen = cv2.imread(tmp_path, cv2.IMREAD_GRAYSCALE)
                try:
                    os.remove(tmp_path)
                except Exception:
                    pass

                if screen is not None:
                    if rect is not None:
                        x, y, w, h = rect
                        # If geometric parsing yields valid off-zero bounds, crop to save performance
                        if (x != 0 or y != 0) and y + h <= screen.shape[0] and x + w <= screen.shape[1]:
                            return screen[y:y+h, x:x+w]
                    return screen  # Return full screen fallback if geometry reports 0,0 under Wayland
                return None
        else:
            # Standard Linux X11 Path
            if sct is None or rect is None:
                return None
            x, y, w, h = rect
            monitor = {"left": x, "top": y, "width": w, "height": h}
            try:
                raw = np.array(sct.grab(monitor))
                return cv2.cvtColor(raw, cv2.COLOR_BGRA2GRAY)
            except Exception as e:
                logger.error("Screenshot failed on X11: %s", e)
                return None

# --- MAIN LOOP ---
def main():
    # Setup Logging to Console only (No separate file)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[logging.StreamHandler()]
    )

    logger.info("=== DOTA 2 BOT INITIALIZATION ===")

    if not IS_WINDOWS and os.environ.get("WAYLAND_DISPLAY"):
        logger.info("[Environment] Wayland session detected. Using CLI compatibility engine for screenshots.")

    # Check Directories & Assets
    if not BTNS_DIR.exists():
        logger.error("Buttons directory not found: %s", BTNS_DIR)
        return 1

    required_templates = [IMG_PLAY, IMG_FIND, IMG_ACCEPT, IMG_LOCK, IMG_OK] + IMG_CONTINUE_LIST
    missing = [t for t in required_templates if not (BTNS_DIR / t).exists()]
    if missing:
        logger.error("Missing templates in btns/: %s", missing)
        return 1

    # Load Heroes
    heroes_input = ""
    if len(sys.argv) > 1:
        heroes_input = " ".join(sys.argv[1:])
        if "," not in heroes_input and " " in heroes_input:
            heroes_input = heroes_input.replace(" ", ", ")
    else:
        heroes_input = os.environ.get("BOT_HEROES", "").strip()

    if not heroes_input:
        try:
            heroes_input = input("Enter heroes separated by commas (e.g., abaddon, pudge): ")
        except (EOFError, KeyboardInterrupt):
            return 130

    hero_list = [h.strip().lower() for h in heroes_input.split(",") if h.strip()]
    if not hero_list:
        logger.error("Hero list cannot be empty.")
        return 1

    logger.info("Hero cycle: %s", " ➔ ".join(h.upper() for h in hero_list))

    # Initialize Cache & Memory
    templates = TemplateCache(BTNS_DIR)
    templates.load(*required_templates)

    killer = Killer()
    state = State.MENU
    hero_index = 0
    match_start_time = 0.0

    logger.info("Bot is ready. Waiting for Dota 2 window...")

    # Safe MSS initialization (Only active for Windows or Linux X11)
    sct = None
    if MSS is not None:
        try:
            sct = MSS()
        except Exception:
            sct = None

    try:
        while not killer.kill_now:
            window_id = get_dota_window()
            if window_id is None:
                logger.info("[Standby] Dota 2 window not found. Waiting...")
                killer.sleep(10)
                continue

            rect = get_window_rect(window_id)
            if rect is None:
                logger.warning("Dota 2 window is minimized or invalid geometry. Waiting...")
                killer.sleep(5)
                continue

            win_x, win_y, _, _ = rect
            screen = capture_window_gray(sct, rect)
            if screen is None:
                killer.sleep(2)
                continue

            # --- GLOBAL CHECKS ---
            # Отлов системных ошибок, обрыва сети или ошибки загрузки лобби
            tpl_ok = templates.get(IMG_OK)
            if tpl_ok is not None and (hit := find_template(screen, tpl_ok)):
                logger.warning("Dismissing 'OK' dialog (Network issue / Disconnect) and returning to MENU.")
                abs_x, abs_y = win_x + hit[0], win_y + hit[1]
                dota_click(window_id, abs_x, abs_y)
                state = State.MENU
                killer.sleep(2)
                continue

            # --- STATE: MENU ---
            if state == State.MENU:
                # 1. Check for Accept Match (Highest priority)
                tpl_acc = templates.get(IMG_ACCEPT)
                if tpl_acc is not None and (hit := find_template(screen, tpl_acc)):
                    logger.info("Match found! Accepting...")
                    abs_x, abs_y = win_x + hit[0], win_y + hit[1]
                    dota_click(window_id, abs_x, abs_y)
                    killer.sleep(2)
                    continue

                # 2. Check for Play Dota
                tpl_play = templates.get(IMG_PLAY)
                if tpl_play is not None and (hit := find_template(screen, tpl_play)):
                    logger.info("Clicking PLAY DOTA...")
                    abs_x, abs_y = win_x + hit[0], win_y + hit[1]
                    dota_click(window_id, abs_x, abs_y)
                    killer.sleep(1.0)
                    logger.info("Clicking FIND MATCH in the same spot...")
                    dota_click(window_id, abs_x, abs_y)
                    killer.sleep(2)
                    continue

                # 3. Check if menu drawer is already open
                tpl_find = templates.get(IMG_FIND)
                if tpl_find is not None and (hit := find_template(screen, tpl_find)):
                    logger.info("Menu open. Clicking FIND MATCH...")
                    abs_x, abs_y = win_x + hit[0], win_y + hit[1]
                    dota_click(window_id, abs_x, abs_y)
                    killer.sleep(2)
                    continue

                # 4. Check if transitioned to Pick screen
                tpl_lock = templates.get(IMG_LOCK)
                if tpl_lock is not None and find_template(screen, tpl_lock):
                    logger.info("Pick screen detected! Switching to PICK state.")
                    state = State.PICK
                    continue

                killer.sleep(2)

            # --- STATE: PICK ---
            elif state == State.PICK:
                current_hero = hero_list[hero_index]
                logger.info("NEW MATCH! Queueing pick: %s", current_hero.upper())

                killer.sleep(4)  # Let animation finish
                dota_type_text(window_id, current_hero)
                killer.sleep(0.5)
                dota_send_key(window_id, "Return")
                killer.sleep(1.5)

                # Fresh screenshot for LOCK button
                screen = capture_window_gray(sct, get_window_rect(window_id))
                tpl_lock = templates.get(IMG_LOCK)
                if screen is not None and tpl_lock is not None and (hit := find_template(screen, tpl_lock)):
                    logger.info("Clicking LOCK IN!")
                    abs_x, abs_y = win_x + hit[0], win_y + hit[1]
                    dota_click(window_id, abs_x, abs_y)
                else:
                    logger.warning("LOCK IN button not visible. Trying Alt+Enter fallback...")
                    dota_send_key(window_id, "alt+Return")

                # Advance queue & transition to MATCH state
                hero_index = (hero_index + 1) % len(hero_list)
                logger.info("Next hero in queue: %s", hero_list[hero_index].upper())
                logger.info("Switching to MATCH state. Game in progress...")

                state = State.MATCH
                match_start_time = time.time()
                killer.sleep(15)  # Wait out the rest of the pick phase

            # --- STATE: MATCH ---
            elif state == State.MATCH:
                # 1. Enforce global match timeout safety
                if time.time() - match_start_time > MATCH_END_TIMEOUT:
                    logger.warning("Match timeout reached (%s sec). Forcing reset to MENU state.", MATCH_END_TIMEOUT)
                    state = State.MENU
                    continue

                match_ended = False
                for tpl_name in IMG_CONTINUE_LIST:
                    tpl = templates.get(tpl_name)
                    if tpl is not None and (hit := find_template(screen, tpl)):
                        logger.info("Match End detected via: %s. Multi-clicking continue flow...", tpl_name)

                        # Multi-stage screen loop to clear MVP/Progress panels seamlessly
                        for _ in range(5):
                            abs_x, abs_y = win_x + hit[0], win_y + hit[1]
                            dota_click(window_id, abs_x, abs_y)
                            killer.sleep(1.5)

                            curr_rect = get_window_rect(window_id)
                            if not curr_rect:
                                break
                            fresh_screen = capture_window_gray(sct, curr_rect)
                            if fresh_screen is None:
                                break

                            hit = None
                            for t_name in IMG_CONTINUE_LIST:
                                t_img = templates.get(t_name)
                                if t_img is not None:
                                    hit = find_template(fresh_screen, t_img)
                                    if hit:
                                        break
                            if not hit:
                                break

                        match_ended = True
                        break

                if match_ended:
                    state = State.MENU
                    logger.info("Returning to MENU.")
                    killer.sleep(5)
                    continue

                # 2. Drop validation (only if the match has been running for at least 2 minutes)
                if time.time() - match_start_time > 120:
                    tpl_play = templates.get(IMG_PLAY)
                    tpl_acc = templates.get(IMG_ACCEPT)
                    if (tpl_play is not None and find_template(screen, tpl_play)) or \
                       (tpl_acc is not None and find_template(screen, tpl_acc)):
                        logger.warning("Main menu detected during active MATCH state. Resetting state to MENU.")
                        state = State.MENU
                        continue

                killer.sleep(3)
    finally:
        if sct is not None:
            try:
                sct.close()
            except Exception:
                pass

    logger.info("Bot stopped gracefully.")
    return 0

if __name__ == "__main__":
    sys.exit(main())
