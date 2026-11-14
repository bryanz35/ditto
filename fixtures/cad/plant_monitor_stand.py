# A desk stand around the plant monitor's case: a wide foot, a backrest rising behind the case and
# a wing over the left wall. The wing and backrest cover the USB port and the soil-probe cable hole;
# code cuts those openings back through them.
from build123d import Align, Box, Pos

L, W, H = CAVITY_MM  # noqa: F821 (predefined for device models)
w = WALL_MM  # noqa: F821
MIN = (Align.MIN, Align.MIN, Align.MIN)

foot = Pos(-w - 20, -w - 10, -w - 4) * Box(L + 2 * w + 40, W + 2 * w + 30, 5, align=MIN)
back = Pos(-w, W + w - 1, -w - 4) * Box(L + 2 * w, 5, H + 2 * w + 40, align=MIN)
wing = Pos(-w - 8, -w, -w - 4) * Box(9, W + 2 * w, H + w + 4, align=MIN)
body = foot + back + wing
