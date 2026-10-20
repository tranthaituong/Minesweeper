"""High-DPI presentation. Window coordinates and physical pixels stay separate."""

import pygame
from pathlib import Path
import os


def enable_real_highdpi(Window):
    """Some pygame 2.6.1 wheels compile this enum as 0; SDL2 specifies 0x2000.

    Fix only this process's Python keyword table, not the installed package.
    Merely passing allow_highdpi=True is ineffective when its flag is zero.
    """
    flags = getattr(Window, "_kwarg_to_flag", None)
    if isinstance(flags, dict) and not flags.get("allow_highdpi"):
        flags["allow_highdpi"] = 0x00002000


def app_icon():
    """Draw a 512 px icon instead of SDL's small default Pygame bitmap."""
    icon = pygame.Surface((512, 512), pygame.SRCALPHA)
    pygame.draw.rect(icon, "#087E83", (8, 8, 496, 496), border_radius=116)
    candidates = [Path('/System/Library/Fonts/Supplemental/Arial Bold.ttf'),
                  Path(os.environ.get('WINDIR', 'C:/Windows'))/'Fonts/arialbd.ttf',
                  Path('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf')]
    path = next((str(path) for path in candidates if path.is_file()), None)
    font = pygame.font.Font(path, 330)
    if path is None:
        font.set_bold(True)
    label = font.render('M', True, '#FFFFFF')
    # Use the actual glyph bounds, not the font's ascent/descent, to center it.
    glyph = label.subsurface(label.get_bounding_rect())
    icon.blit(glyph, glyph.get_rect(center=(256, 256)))
    return icon


class NativeDisplay:
    def __init__(self, size, title):
        self.window = None
        self.renderer = None
        self.texture = None
        self.surface = None
        self.fallback_reason = None
        SDLError = pygame.error
        try:
            from pygame._sdl2 import Window, Renderer
            from pygame._sdl2.sdl2 import error as SDLError
            enable_real_highdpi(Window)
            self.window = Window(title, size=size, resizable=True, allow_highdpi=True)
            self.window.set_icon(app_icon())
            try:
                self.renderer = Renderer(self.window, accelerated=True, vsync=False)
            except (pygame.error, SDLError):
                self.renderer = Renderer(self.window, accelerated=False)
        except (ImportError, pygame.error, TypeError, SDLError) as exc:
            self.fallback_reason = str(exc)
            self.close()
            self.surface = pygame.display.set_mode(size, pygame.RESIZABLE)
            pygame.display.set_caption(title)
            pygame.display.set_icon(app_icon())

    @property
    def window_size(self):
        return tuple(self.window.size) if self.window else pygame.display.get_window_size()

    @property
    def pixel_size(self):
        if self.renderer:
            # With no logical-size scaling, the default viewport covers physical
            # drawable pixels, including 2x Retina backing pixels.
            self.renderer.set_viewport(None)
            return self.renderer.get_viewport().size
        return self.surface.get_size()

    def resize(self, size):
        if self.window:
            if tuple(self.window.size) != tuple(size):
                self.window.size = size
        else:
            self.surface = pygame.display.set_mode(size, pygame.RESIZABLE)

    def present(self, pixels):
        if self.renderer:
            from pygame._sdl2 import Texture
            if self.texture is None or (self.texture.width, self.texture.height) != pixels.get_size():
                self.texture = Texture(self.renderer, pixels.get_size(), streaming=True)
            self.texture.update(pixels)
            self.renderer.draw_color = (243, 245, 248, 255)
            self.renderer.clear()
            # Canvas and viewport have identical pixel dimensions: no bitmap upscaling.
            self.texture.draw(dstrect=pygame.Rect((0, 0), pixels.get_size()))
            self.renderer.present()
        else:
            self.surface.blit(pixels, (0, 0))
            pygame.display.flip()

    def close(self):
        self.texture = None
        self.renderer = None
        if self.window:
            self.window.destroy()
            self.window = None
