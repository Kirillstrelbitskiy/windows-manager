#!/usr/bin/env python3
from typing import Any, Dict, List
from AppKit import NSScreen
from AppKit import NSRunningApplication, NSApplicationActivateIgnoringOtherApps
from Quartz import (
    CGWindowListCopyWindowInfo,
    kCGWindowListOptionOnScreenOnly,
    kCGWindowListExcludeDesktopElements,
    kCGNullWindowID,
    CGEventTapCreate,
    CGEventMaskBit,
    CFMachPortCreateRunLoopSource,
    CFRunLoopAddSource,
    CFRunLoopGetCurrent,
    CFRunLoopRun,
    kCFRunLoopCommonModes,
    CGEventTapEnable,
    CGEventGetFlags,
    CGEventGetIntegerValueField,
    kCGKeyboardEventKeycode,
    kCGEventKeyDown,
    kCGSessionEventTap,
    kCGHeadInsertEventTap,
    kCGEventFlagMaskControl,
    kCGEventFlagMaskAlternate,
    kCGEventFlagMaskCommand,
)
from ApplicationServices import (
    AXUIElementCreateSystemWide,
    AXUIElementCopyAttributeValue,
    AXUIElementCreateApplication,
    AXUIElementSetAttributeValue,
    AXUIElementPerformAction,
    AXValueGetValue,
    kAXFocusedApplicationAttribute,
    kAXFocusedWindowAttribute,
    kAXWindowsAttribute,
    kAXPositionAttribute,
    kAXSizeAttribute,
    kAXRaiseAction,
    kAXValueCGPointType,
    kAXValueCGSizeType,
)

def _cg_to_cocoa_bounds(bounds: Dict[str, Any]) -> Dict[str, int]:
    try:
        main_screen = NSScreen.mainScreen()
        if main_screen is None:
            raise RuntimeError("No main screen")
        frame = main_screen.frame()  # NSRect
        screen_height = int(frame.size.height)
        x = int(bounds.get("X", 0))
        y_cg = int(bounds.get("Y", 0))
        w = int(bounds.get("Width", 0))
        h = int(bounds.get("Height", 0))
        y_cocoa = screen_height - (y_cg + h)
        return {"x": x, "y": y_cocoa, "width": w, "height": h}
    except Exception:
        return {
            "x": int(bounds.get("X", 0)),
            "y": int(bounds.get("Y", 0)),
            "width": int(bounds.get("Width", 0)),
            "height": int(bounds.get("Height", 0)),
        }

def list_visible_windows(include_untitled: bool = False) -> List[Dict[str, Any]]:
    options = kCGWindowListOptionOnScreenOnly | kCGWindowListExcludeDesktopElements
    info_list = CGWindowListCopyWindowInfo(options, kCGNullWindowID) or []
    results: List[Dict[str, Any]] = []

    for win in info_list:
        if win.get("kCGWindowLayer", 0) != 0:
            continue
        if win.get("kCGWindowAlpha", 1) <= 0:
            continue

        bounds = win.get("kCGWindowBounds") or {}
        if not bounds or bounds.get("Width", 0) == 0 or bounds.get("Height", 0) == 0:
            continue

        title = win.get("kCGWindowName", "") or ""
        if not include_untitled and not title.strip():
            continue

        owner = win.get("kCGWindowOwnerName", "") or ""
        pid = int(win.get("kCGWindowOwnerPID", 0))

        cg_bounds = {
            "x": int(bounds.get("X", 0)),
            "y": int(bounds.get("Y", 0)),
            "width": int(bounds.get("Width", 0)),
            "height": int(bounds.get("Height", 0)),
        }
        cocoa_bounds = _cg_to_cocoa_bounds(bounds)

        results.append(
            {
                "app": owner,
                "pid": pid,
                "title": title,
                "bounds_cg": cg_bounds,
                "bounds_cocoa": cocoa_bounds,
            }
        )

    return results


def _get_global_cocoa_max_y() -> float:
    screens = NSScreen.screens()
    if not screens:
        return 0.0
    return float(max((s.frame().origin.y + s.frame().size.height) for s in screens))

def _cg_bounds_to_cocoa_global(bounds: Dict[str, Any]) -> Dict[str, float]:
    max_y = _get_global_cocoa_max_y()
    x = float(bounds.get("X", 0))
    y_top = float(bounds.get("Y", 0))
    w = float(bounds.get("Width", 0))
    h = float(bounds.get("Height", 0))
    y_bottom = max_y - (y_top + h)
    return {"x": x, "y": y_bottom, "width": w, "height": h}

def _ax_copy_attr(element, attr):
    err, value = AXUIElementCopyAttributeValue(element, attr, None)
    return value if err == 0 else None

def _ax_get_window_frame(ax_window) -> Dict[str, float] | None:
    pos_val = _ax_copy_attr(ax_window, kAXPositionAttribute)
    size_val = _ax_copy_attr(ax_window, kAXSizeAttribute)
    if not pos_val or not size_val:
        return None
    ok_pos, pos = AXValueGetValue(pos_val, kAXValueCGPointType, None)
    ok_size, size = AXValueGetValue(size_val, kAXValueCGSizeType, None)
    if not ok_pos or not ok_size or pos is None or size is None:
        return None

    px = float(getattr(pos, "x", pos[0]))
    py = float(getattr(pos, "y", pos[1]))
    pw = float(getattr(size, "width", size[0]))
    ph = float(getattr(size, "height", size[1]))
    return {"x": px, "y": py, "width": pw, "height": ph}

def _get_focused_window_frame_and_pid() -> tuple[Dict[str, float] | None, int | None]:
    sys = AXUIElementCreateSystemWide()
    app = _ax_copy_attr(sys, kAXFocusedApplicationAttribute)
    if not app:
        return None, None
    win = _ax_copy_attr(app, kAXFocusedWindowAttribute)
    if not win:
        return None, None
    frame = _ax_get_window_frame(win)
    return frame, None

def _frames_close(a: Dict[str, float], b: Dict[str, float], tol: float = 8.0) -> bool:
    return (
        abs(a["x"] - b["x"]) <= tol
        and abs(a["y"] - b["y"]) <= tol
        and abs(a["width"] - b["width"]) <= tol
        and abs(a["height"] - b["height"]) <= tol
    )

def _focus_window_by_pid_and_bounds(pid: int, target_frame: Dict[str, float]) -> None:
    try:
        app_ax = AXUIElementCreateApplication(pid)
        err, ax_windows = AXUIElementCopyAttributeValue(app_ax, kAXWindowsAttribute, None)
        if err != 0 or not ax_windows:
            return

        selected = None
        for axw in ax_windows:
            f = _ax_get_window_frame(axw)
            if not f:
                continue
            if _frames_close(f, target_frame, tol=8.0):
                selected = axw
                break

        if not selected:
            def center(b): return (b["x"] + b["width"]/2.0, b["y"] + b["height"]/2.0)
            tx, ty = center(target_frame)
            best = None
            best_d2 = None
            for axw in ax_windows:
                f = _ax_get_window_frame(axw)
                if not f:
                    continue
                cx, cy = center(f)
                d2 = (cx - tx) ** 2 + (cy - ty) ** 2
                if best_d2 is None or d2 < best_d2:
                    best, best_d2 = axw, d2
            selected = best

        if selected:
            AXUIElementPerformAction(selected, kAXRaiseAction)
            AXUIElementSetAttributeValue(app_ax, kAXFocusedWindowAttribute, selected)
            try:
                NSRunningApplication.runningApplicationWithProcessIdentifier_(pid).activateWithOptions_(NSApplicationActivateIgnoringOtherApps)
            except Exception:
                pass
    except Exception:
        pass

def _center(b: Dict[str, float]) -> tuple[float, float]:
    return (b["x"], b["y"])

def focus_adjacent_window(direction: str) -> None:
    cur_frame, _ = _get_focused_window_frame_and_pid()
    if not cur_frame:
        return

    wins = list_visible_windows(include_untitled=True)
    for w in wins:
        cg = w["bounds_cg"]
        cocoa = _cg_bounds_to_cocoa_global(
            {"X": cg["x"], "Y": cg["y"], "Width": cg["width"], "Height": cg["height"]}
        )
        w["_cocoa"] = cocoa

    cx, cy = _center(cur_frame)

    def vertical_overlap(a: Dict[str, float], b: Dict[str, float]) -> float:
        a_top = a["y"] + a["height"]
        b_top = b["y"] + b["height"]
        overlap = min(a_top, b_top) - max(a["y"], b["y"])
        return max(0, overlap)

    def horizontal_overlap(a: Dict[str, float], b: Dict[str, float]) -> float:
        a_right = a["x"] + a["width"]
        b_right = b["x"] + b["width"]
        overlap = min(a_right, b_right) - max(a["x"], b["x"])
        return max(0, overlap)

    if direction == "right":
        cand = [w for w in wins if _center(w["_cocoa"])[0] > cx and vertical_overlap(w["_cocoa"], cur_frame) > 0]
    elif direction == "left":
        cand = [w for w in wins if _center(w["_cocoa"])[0] < cx and vertical_overlap(w["_cocoa"], cur_frame) > 0]
    elif direction == "up":
        cand = [w for w in wins if _center(w["_cocoa"])[1] > cy and horizontal_overlap(w["_cocoa"], cur_frame) > 0]
    else:
        cand = [w for w in wins if _center(w["_cocoa"])[1] < cy and horizontal_overlap(w["_cocoa"], cur_frame) > 0]

    target = None
    if cand:
        if direction == "right":
            cand.sort(key=lambda w: (_center(w["_cocoa"])[0] - cx, abs(_center(w["_cocoa"])[1] - cy)))
        elif direction == "left":
            cand.sort(key=lambda w: (cx - _center(w["_cocoa"])[0], abs(_center(w["_cocoa"])[1] - cy)))
        elif direction == "up":
            cand.sort(key=lambda w: (_center(w["_cocoa"])[1] - cy, abs(_center(w["_cocoa"])[0] - cx)))
        else:
            cand.sort(key=lambda w: (cy - _center(w["_cocoa"])[1], abs(_center(w["_cocoa"])[0] - cx)))
        target = cand[0]
    elif wins:
        if direction == "right":
            target = min(wins, key=lambda w: _center(w["_cocoa"])[0])
        elif direction == "left":
            target = max(wins, key=lambda w: _center(w["_cocoa"])[0])
        elif direction == "up":
            target = min(wins, key=lambda w: _center(w["_cocoa"])[1])
        else:
            target = max(wins, key=lambda w: _center(w["_cocoa"])[1])

    if target:
        _focus_window_by_pid_and_bounds(target["pid"], target["_cocoa"])


KEY_LEFT = 123
KEY_RIGHT = 124
KEY_DOWN = 125
KEY_UP = 126

REQUIRED_CTRL_OPT = kCGEventFlagMaskControl | kCGEventFlagMaskAlternate
REQUIRED_CTRL_OPT_CMD = REQUIRED_CTRL_OPT | kCGEventFlagMaskCommand

def handle_ctrl_opt_left() -> None:
    focus_adjacent_window("left")

def handle_ctrl_opt_right() -> None:
    focus_adjacent_window("right")

def handle_ctrl_opt_up() -> None:
    focus_adjacent_window("up")

def handle_ctrl_opt_down() -> None:
    focus_adjacent_window("down")

def _has_modifiers(flags: int, required: int, forbidden: int = 0) -> bool:
    return (flags & required) == required and (flags & forbidden) == 0

def _event_tap_callback(proxy, type_, event, refcon):
    if type_ != kCGEventKeyDown:
        return event
    flags = CGEventGetFlags(event)
    keycode = CGEventGetIntegerValueField(event, kCGKeyboardEventKeycode)

    if _has_modifiers(flags, REQUIRED_CTRL_OPT):
        if keycode == KEY_LEFT:
            handle_ctrl_opt_left()
            return None
        elif keycode == KEY_RIGHT:
            handle_ctrl_opt_right()
            return None
        elif keycode == KEY_UP:
            handle_ctrl_opt_up()
            return None
        elif keycode == KEY_DOWN:
            handle_ctrl_opt_down()
            return None

    return event


_event_tap = None
_run_loop_source = None

def start_hotkey_listener() -> None:
    global _event_tap, _run_loop_source
    event_mask = CGEventMaskBit(kCGEventKeyDown)
    _event_tap = CGEventTapCreate(
        kCGSessionEventTap,
        kCGHeadInsertEventTap,
        0,
        event_mask,
        _event_tap_callback,
        None,
    )
    if not _event_tap:
        raise RuntimeError(
            "Failed to create event tap. Grant Accessibility permissions to your Python/Terminal."
        )
    _run_loop_source = CFMachPortCreateRunLoopSource(None, _event_tap, 0)
    CFRunLoopAddSource(CFRunLoopGetCurrent(), _run_loop_source, kCFRunLoopCommonModes)
    CGEventTapEnable(_event_tap, True)
    CFRunLoopRun()

if __name__ == "__main__":
    import sys
    import os
    windows = list_visible_windows(include_untitled=False)

    print("Starting hotkey listener...")
    print("Use Ctrl+Option+Arrow keys to navigate between windows")
    start_hotkey_listener()
