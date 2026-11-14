"""Shared base model and coordinate conventions for every contract.

Coordinate frames (all lengths in mm):

- Part frame: origin at the front-left-bottom corner of the part's bounding box (`PartDef.board_mm`,
  including pin headers). x runs along `l`, y along `w`, z up. Faces: front is the y=0 side, back y=w,
  left x=0, right x=l, top z=h.
- Enclosure frame: origin at the front-left corner of the cavity floor (inside the walls). x runs along
  the cavity length, y toward the back, z up. Walls: front at y=0, back at y=W, left at x=0, right at
  x=L; "top" is the lid.
- Face-plane coordinates (u, v) on a face: top (x, y); front and back (x, z); left and right (y, z).
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict

Face = Literal["top", "front", "back", "left", "right"]
Wall = Literal["front", "back", "left", "right"]


class Model(BaseModel):
    """Base for contract models: unknown fields are errors, and attribute docstrings become schema
    descriptions (they reach the TypeScript types and the agents' structured output)."""

    model_config = ConfigDict(
        extra="forbid",
        use_attribute_docstrings=True,
        json_schema_serialization_defaults_required=True,
    )
