"""
palettes.py
===========

Color palettes for the light show. Each is a list of (hue, saturation)
pairs. Brightness comes from the band envelope at runtime.
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import List, Tuple


@dataclass(frozen=True)
class Palette:
    name: str
    slots: List[Tuple[int, int]]


PALETTES: List[Palette] = [
    Palette("Sunset Drop",     [(15, 100), (280, 90)]),
    Palette("Ocean Pulse",     [(200, 95), (310, 80)]),
    Palette("Lava Vein",       [(0, 100), (35, 100)]),
    Palette("Aurora",          [(150, 90), (260, 90)]),
    Palette("Hot Pink Heat",   [(330, 100), (10, 95)]),
    Palette("Deep Sea",        [(220, 100), (180, 95)]),
    Palette("Cyan Dream",      [(190, 95), (240, 85)]),
    Palette("Forest Floor",    [(110, 80), (40, 70)]),
    Palette("Pine Frost",      [(160, 80), (200, 90)]),
    Palette("Golden Hour",     [(40, 90), (15, 95)]),
    Palette("Desert Bloom",    [(25, 85), (340, 80)]),
    Palette("Amber Glow",      [(30, 100), (50, 90)]),
    Palette("Neon Punk",       [(300, 100), (90, 100)]),
    Palette("Cyber Lime",      [(75, 100), (290, 100)]),
    Palette("Hot Wire",        [(0, 100), (300, 100)]),
    Palette("Vapor Wave",      [(290, 100), (180, 100)]),
    Palette("Cotton Candy",    [(330, 60), (200, 60)]),
    Palette("Pastel Dawn",     [(40, 50), (320, 55)]),
    Palette("Soft Mint",       [(150, 50), (260, 50)]),
    Palette("Blood Moon",      [(355, 100), (270, 100)]),
    Palette("Dark Forest",     [(120, 100), (260, 90)]),
    Palette("Indigo Night",    [(250, 100), (210, 90)]),
    Palette("Jazz Lounge",     [(35, 85), (300, 75)]),
    Palette("Metal Forge",     [(0, 100), (25, 100)]),
    Palette("Ambient Drift",   [(190, 60), (260, 60)]),
    Palette("Electronic",      [(290, 100), (170, 100)]),
    Palette("Folk Hearth",     [(30, 80), (15, 70)]),
    Palette("Pure Red",        [(0, 100), (0, 100)]),
    Palette("Pure Cyan",       [(180, 100), (180, 100)]),
    Palette("Pure Magenta",    [(300, 100), (300, 100)]),
    Palette("Rainbow Split",   [(0, 100), (240, 100)]),
    Palette("Triadic Pop",     [(0, 100), (120, 100), (240, 100)]),
    Palette("Complement",      [(180, 100), (0, 100)]),
]


def palette_by_name(name: str) -> Palette:
    for p in PALETTES:
        if p.name == name:
            return p
    return PALETTES[0]


def slot_for_bulb(palette: Palette, bulb_index: int) -> Tuple[int, int]:
    return palette.slots[bulb_index % len(palette.slots)]
