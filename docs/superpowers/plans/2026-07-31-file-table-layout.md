# WxCleaner File Table Layout Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the WxCleaner file table use one shared column geometry for its fixed header and scrolling rows while preserving the existing selection and macOS scrolling behavior.

**Architecture:** Keep the existing `Canvas + CTkFrame` table instead of changing the widget stack. Put the header and body canvas in the same horizontal grid viewport, put the scrollbar in a separate grid column, and configure the header plus every row with the same fixed/weighted columns. The path column is the only flexible column and receives a minimum width so the fixed metadata columns remain stable.

**Tech Stack:** Python 3, Tkinter, CustomTkinter, pytest, macOS Tk 8.6 test environment.

---

### Task 1: Add geometry regression tests

**Files:**
- Modify: `/Users/m2222/Downloads/WxCleaner-1.0.0/tests/test_gui_table.py`
- Test target: `FileTable` header and row geometry after Tk layout calculation

- [ ] **Step 1: Add a helper that creates the full five-column table.**

Use the existing `tk_root` fixture and create a table with columns `("num", "path", "size", "mtime", "status")`, widths `(60, 0, 110, 170, 80)`, one long path row, and a second row. Set the root geometry large enough for the documented path minimum before calling `update_idletasks()`.

- [ ] **Step 2: Add a failing test for shared header/row cell bounds.**

Compare `winfo_x()` and `winfo_width()` for each header label and the corresponding first-row label. Assert that all five pairs match after layout. The current `pack` implementation should fail because it does not create fixed-width grid tracks.

- [ ] **Step 3: Add a failing test for path-only resizing.**

Record the first-row label widths at a wide window, shrink and enlarge the root, and assert that the `path` label changes width while `num`, `size`, `mtime`, and `status` label widths stay unchanged. Restore the fixture geometry in the `finally` block.

- [ ] **Step 4: Run the focused tests and verify they fail for the old layout.**

Run:

```bash
pytest -q tests/test_gui_table.py -k "shared_header_row_geometry or path_column_resizes"
```

Expected: the new geometry assertions fail before the implementation changes.

### Task 2: Implement shared grid geometry

**Files:**
- Modify: `/Users/m2222/Downloads/WxCleaner-1.0.0/source/wx_gui.py:106-205`

- [ ] **Step 1: Add one column configuration source.**

Store per-column grid settings derived from `self.col_keys` and `self.col_widths`. A width of `0` is the flexible column; give the path column a `minsize` of `180`, `weight=1`, and `minsize=0` for other zero-width columns. Positive widths use `weight=0` and their supplied width as `minsize`.

- [ ] **Step 2: Put header and body canvas in one horizontal viewport.**

Replace the current `pack` calls for the header, separator, canvas, and scrollbar with a parent grid:

```python
self.grid_columnconfigure(0, weight=1)
self.grid_rowconfigure(2, weight=1)
self._header.grid(row=0, column=0, sticky="ew", padx=(4, 0), pady=(4, 2))
self._separator.grid(row=1, column=0, sticky="ew", padx=(4, 0))
self._canvas.grid(row=2, column=0, sticky="nsew", padx=(4, 0), pady=2)
self._scroll.grid(row=2, column=1, sticky="ns", padx=(0, 2), pady=2)
```

The header and canvas then receive the same usable width; the scrollbar does not consume a hidden part of the header's column geometry.

- [ ] **Step 3: Configure the header grid from the shared settings.**

Call `grid_columnconfigure(index, minsize=minsize, weight=weight)` on the header. Create each header label with the same `(8, 4)` horizontal padding and `sticky="ew"`, keeping text alignment separate from cell geometry. Store header labels in `self._header_cells` for layout testing and diagnostics.

- [ ] **Step 4: Configure each row with the same grid settings.**

Call the same column configuration helper for every row frame, use `grid(row=0, column=index, sticky="ew", padx=(8, 4))` for each label, and keep each row at `S.ROW_H` with `grid_propagate(False)`. Store row labels in the existing `labels` mapping so all selection, tagging, and click behavior remains unchanged.

- [ ] **Step 5: Run the focused geometry and existing table tests.**

Run:

```bash
pytest -q tests/test_gui_table.py
```

Expected: all table tests pass, with the Tk 9-only touchpad test skipped when the local Tk build does not expose `<TouchpadScroll>`.

### Task 3: Verify the full workflow and visual result

**Files:**
- Inspect: `/Users/m2222/Downloads/WxCleaner-1.0.0/source/wx_gui.py`
- Inspect: `/Users/m2222/Downloads/WxCleaner-1.0.0/tests/test_gui_lifecycle.py`

- [ ] **Step 1: Run the complete test suite.**

Run:

```bash
pytest -q
```

Expected: the complete suite passes, with only capability-based Tk 9 skips permitted.

- [ ] **Step 2: Start the actual GUI and inspect both wide and narrow layouts.**

Launch the existing application entry point, populate or scan enough rows to make the body scrollable, and verify that the header remains fixed, the path column absorbs width changes, the right-side columns remain aligned, and the bottom progress/action area stays fixed.

- [ ] **Step 3: Verify wheel and selection behavior after layout changes.**

Use the local Tk event tests and a real macOS interaction check to verify that row labels still select rows and that small versus large mouse/trackpad deltas produce different scroll distances. Do not claim direct Tk 9 hardware verification on the local Tk 8.6 build.

- [ ] **Step 4: Review the final diff for unrelated changes.**

Run:

```bash
git diff --check
git diff -- source/wx_gui.py tests/test_gui_table.py docs/superpowers/specs/2026-07-31-file-table-layout-design.md
```

Confirm that only the approved table layout, focused tests, and design documentation changed; leave existing unrelated untracked Vibe artifacts untouched.
