# Topology-Aware Display Finalization Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Split display switching into transition-safe activation and post-disable finalization so framebuffer shrink only happens after the old output is off.

**Architecture:** Keep `DisplayManager.py` focused on low-level RandR primitives and explicit single-output finalization. Move topology sequencing responsibility to `mode_switch.py`, where switch intent is already known. During a switch, first activate the target output in a transition-safe way, then disable the old output, then apply one final compact single-output layout and verify that steady state.

**Tech Stack:** Python 3, `unittest`, `unittest.mock`, `xrandr`, existing `DisplayManager` / `mode_switch` modules

---

### Task 1: Add failing switch-flow tests for post-disable finalization

**Files:**
- Modify: `tests/test_mode_switch_rotation.py`
- Reference: `mode_switch.py`

**Step 1: Write the failing test**

Add one test for `switch_to_eink(...)` and one for `switch_to_oled(...)` proving the switch flow performs a final compact-layout call only after disabling the old output.

```python
self.display_mgr.enable_display.assert_called_once_with(mode_switch.DISPLAY_EINK, scale=1.75)
self.display_mgr.disable_display.assert_called_once_with(mode_switch.DISPLAY_OLED)
self.display_mgr.finalize_single_display.assert_called_once_with(mode_switch.DISPLAY_EINK, scale=1.75)
```

and:

```python
self.display_mgr.enable_display.assert_called_once_with(mode_switch.DISPLAY_OLED, scale=1.75)
self.display_mgr.disable_display.assert_called_once_with(mode_switch.DISPLAY_EINK)
self.display_mgr.finalize_single_display.assert_called_once_with(mode_switch.DISPLAY_OLED, scale=1.75)
```

Also assert ordering with `mock_calls` or call indices so finalization is after the disable step.

**Step 2: Run test to verify it fails**

Run:
```bash
python -m unittest tests.test_mode_switch_rotation -v
```

Expected: FAIL because `DisplayManager` has no `finalize_single_display(...)` call in switch flow yet.

**Step 3: Write minimal implementation**

Do not touch production code yet beyond what is needed for the tests to compile if a temporary stub is unavoidable.

**Step 4: Run test to verify it still fails for the right reason**

Run:
```bash
python -m unittest tests.test_mode_switch_rotation -v
```

Expected: FAIL specifically on missing finalization behavior or wrong call order.

**Step 5: Commit**

Do not commit yet. This task is intentionally left red until production changes land.

---

### Task 2: Add failing `DisplayManager` tests for explicit single-output finalization

**Files:**
- Modify: `tests/test_display_manager_rotation.py`
- Reference: `DisplayManager.py`

**Step 1: Write the failing test**

Add tests for a new `finalize_single_display(display_name, scale)` method proving:
- scaled dimensions are rounded up with `math.ceil(...)`
- the resulting xrandr command includes `--mode`, `--scale`, `--panning`, and `--fb`
- `--fb` matches the final single-output logical size

Example target assertion for E-Ink at `1.75`:

```python
ok = self.manager.finalize_single_display("eDP-2", scale=1.75)
self.assertTrue(ok)
command = run_mock.call_args.args[0]
self.assertIn("--fb", command)
self.assertIn("1463x915", command)
```

Add one verification test proving final-state verification succeeds for:

```text
Screen 0: minimum 8 x 8, current 1463 x 915, maximum 32767 x 32767
eDP-2 connected primary 1463x915+0+0 normal (...)
```

**Step 2: Run test to verify it fails**

Run:
```bash
python -m unittest tests.test_display_manager_rotation -v
```

Expected: FAIL because `finalize_single_display(...)` does not exist and current target-state math floors instead of ceils.

**Step 3: Write minimal implementation**

Do not implement yet beyond the minimum needed to keep tests focused on the desired behavior.

**Step 4: Run test to verify it still fails for the right reason**

Run:
```bash
python -m unittest tests.test_display_manager_rotation -v
```

Expected: FAIL on missing finalization behavior or incorrect `1462x914` sizing.

**Step 5: Commit**

Do not commit yet. This task remains red until production code lands.

---

### Task 3: Refactor `DisplayManager` into activation vs. finalization primitives

**Files:**
- Modify: `DisplayManager.py`
- Test: `tests/test_display_manager_rotation.py`

**Step 1: Implement transition-safe activation behavior**

Adjust `enable_display(display_name, scale=None)` so it no longer tries to force the final compact single-output framebuffer during activation.

Keep the behavior narrow:
- activate the output and requested mode/scale in a transition-safe way
- do not shrink framebuffer to a single-output steady state while another output may still be active
- keep unknown-display `--auto` fallback unchanged

If needed, introduce a private helper such as:

```python
def _activate_display_transition_safe(self, display_name, scale=None):
    ...
```

**Step 2: Implement explicit single-output finalization**

Add:

```python
def finalize_single_display(self, display_name, scale=None):
    ...
```

This method should:
- compute logical width/height using `math.ceil(native / scale)`
- build one exact final target state for one active output
- run `xrandr` with `--mode`, `--scale`, `--panning`, `--fb`
- verify the final steady state after the apply
- return `True` only if final-state verification passes

**Step 3: Keep verification focused on steady state**

Reuse or simplify the current verification helpers so the strongest verification is performed from `finalize_single_display(...)`, not from the transition-safe activation path.

Expected final verified state shape:
- framebuffer equals final logical size
- target output geometry equals final logical size
- target output is active

**Step 4: Run targeted tests**

Run:
```bash
python -m unittest tests.test_display_manager_rotation -v
```

Expected: PASS

**Step 5: Commit**

```bash
git add DisplayManager.py tests/test_display_manager_rotation.py
git commit -m "refactor(display): split activation from finalization"
```

---

### Task 4: Update mode-switch sequencing to finalize only after old output is off

**Files:**
- Modify: `mode_switch.py`
- Test: `tests/test_mode_switch_rotation.py`

**Step 1: Update `switch_to_eink(...)` sequencing**

After successful helper enable and after `disable_display(DISPLAY_OLED)`, add:

```python
if not display_mgr.finalize_single_display(DISPLAY_EINK, scale=scale):
    logger.error("Failed to finalize E-Ink output layout")
    return False
```

Do this before touch reconciliation / orientation / post-switch snapshot logging.

**Step 2: Update `switch_to_oled(...)` sequencing**

After successful `disable_display(DISPLAY_EINK)`, add:

```python
if not display_mgr.finalize_single_display(DISPLAY_OLED, scale=scale):
    logger.error("Failed to finalize OLED output layout")
    return False
```

Also place this before touch reconciliation / orientation / snapshot logging.

**Step 3: Keep existing orchestration behavior intact**

Do not change unrelated responsibilities:
- helper commands
- theme switching
- DPMS handling
- privacy image flow
- touch reconciliation
- orientation application
- snapshot logging

Only insert the new explicit post-disable finalization step.

**Step 4: Run targeted tests**

Run:
```bash
python -m unittest tests.test_mode_switch_rotation -v
```

Expected: PASS

**Step 5: Commit**

```bash
git add mode_switch.py tests/test_mode_switch_rotation.py
git commit -m "fix(mode-switch): finalize layout after old output is disabled"
```

---

### Task 5: Run combined regression verification

**Files:**
- No code changes required

**Step 1: Run the full targeted test set**

Run:
```bash
python -m unittest tests.test_display_manager_rotation tests.test_mode_switch_rotation -v
```

Expected: all tests PASS.

**Step 2: Reproduce via CLI on real hardware**

Run:
```bash
python toggle-eink.py
xrandr --query
xrandr --listactivemonitors
```

Expected after switching to E-Ink:
- exit code `0`
- no `specified screen ... not large enough` error
- `Screen 0: current 1463 x 915` (or whatever final ceil-based steady state is for current configured scale)
- only E-Ink active in `--listactivemonitors`

Then run the reverse direction:

```bash
python toggle-eink.py
xrandr --query
xrandr --listactivemonitors
```

Expected after switching back to OLED:
- exit code `0`
- no clipping
- one active OLED monitor
- framebuffer matches final OLED-only logical geometry

**Step 3: If hardware verification fails, stop and capture evidence**

Collect:
```bash
python toggle-eink.py 2>&1 | tee /tmp/toggle-eink.log
xrandr --query > /tmp/xrandr-query.txt
xrandr --listactivemonitors > /tmp/xrandr-monitors.txt
```

Do not guess. Inspect the actual topology and update the design only if evidence shows a new failure mode.

**Step 4: Commit final integrated change if verification passes**

```bash
git add DisplayManager.py mode_switch.py tests/test_display_manager_rotation.py tests/test_mode_switch_rotation.py
git commit -m "fix(display): finalize single-output layout after switch"
```

**Step 5: Summarize verification evidence**

Record in the handoff note:
- exact unittest command run
- exact CLI commands run
- final `xrandr --query` steady-state lines for both directions
- confirmation that clipping no longer occurs
