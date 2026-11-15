# Hardware availability

Filled in by the humans at H0 (by hour 2). Agents read this file; only humans edit it.
See "Hardware availability" in `docs/PROJECT_PLAN.md` for what each mode changes.

```
HAS_PARTS=unknown        # yes | no   (our own kit counts)
HAS_PRINTER=unknown      # yes | no
PRINTER_MODEL=generic    # profile id in backend/parts/printers/, e.g. generic
MODE=unknown             # P (parts + printer) | E (parts, no printer) | V (no parts)
SIMULATE=auto            # auto = on in modes E and V, off in P; or on | off
DECIDED_AT_HOUR=
NOTES=
```

Until this is filled in, agents build for mode V (the strictest: datasheet dimensions, generic printer,
simulation available), which also works in modes E and P.
