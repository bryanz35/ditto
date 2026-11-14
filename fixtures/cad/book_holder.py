# A tilted stand for an A5 paperback (148 x 210 mm): a back plate leaning 15 degrees,
# a ledge along the front edge to hold the pages, and two side feet.
from build123d import Box, Pos, Rot

BOOK_W = 148.0  # A5 width
PLATE_H = 160.0  # back plate height, below the book's top edge
T = 4.0  # plate thickness
LEAN = 15.0  # degrees back from vertical

plate = Pos(0, 0, PLATE_H / 2) * Rot(-LEAN, 0, 0) * Box(BOOK_W, T, PLATE_H)
base = Pos(0, 20, T / 2) * Box(BOOK_W, 70, T)
ledge = Pos(0, -13, 12) * Box(BOOK_W, T, 20)
foot = Box(T, 60, 40)
holder = base + plate + ledge + Pos(-BOOK_W / 2 + T / 2, 30, 20) * foot
holder += Pos(BOOK_W / 2 - T / 2, 30, 20) * foot
# Sit it on the bed.
holder = Pos(0, 0, -holder.bounding_box().min.Z) * holder

parts = {"holder": holder}
