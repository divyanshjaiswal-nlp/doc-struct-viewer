"""
Keeping widget state alive across page switches.

Streamlit garbage-collects the session-state entry of any widget that did NOT render on
the current run. In a multi-page app that means every control on the page you just left is
discarded, so coming back to it shows an empty patient id and a reset entity and record.

`keep()` re-assigns every key each run, which marks it app-owned rather than widget-owned
and exempts it from that cleanup. `sticky()` then gives a widget a stable key while
handling the one case re-assignment cannot: a stored choice that is no longer among the
options, e.g. the entity picked for the previous patient.
"""
from __future__ import annotations

import os
from typing import Any, Sequence

import streamlit as st


def is_dark() -> bool | None:
    """
    Whether the APP is in dark mode -- None when Streamlit cannot say.

    Needed because a components.html iframe resolves `prefers-color-scheme` from the
    browser, not from Streamlit's theme, so a dark app on a light OS renders those pages
    with near-black text on a dark background. The page builders take this and stamp it on
    <html> instead of trusting the media query.
    """
    try:
        return st.context.theme.type == "dark"
    except Exception:
        # older Streamlit, or no script run context (a headless import)
        return None


def keep() -> None:
    """Re-register every session-state key so this run's absent widgets survive."""
    for key in list(st.session_state.keys()):
        try:
            st.session_state[key] = st.session_state[key]
        except Exception:
            # a few internal keys are not writable; they are not ours to preserve
            pass


def sticky(container: Any, label: str, options: Sequence[Any], key: str, **kwargs) -> Any:
    """
    A selectbox whose choice survives a page switch.

    Drops the stored value first when it is not in `options` -- otherwise Streamlit is
    asked to restore a selection that no longer exists, which is what happens every time
    the patient changes.
    """
    options = list(options)
    if key in st.session_state and st.session_state[key] not in options:
        del st.session_state[key]

    if not options:
        return None
    return container.selectbox(label, options, key=key, **kwargs)


def paths_expander(dir_vars: Sequence[str], optional: Sequence[str] = ()) -> None:
    """
    The "Paths" expander, rendered by whichever page owns these directories.

    Each page shows only the directories it reads, so a path sits next to the thing it
    feeds. The widget keys stay global (`dir_<VAR>`), so a directory shared between pages
    -- PATIENT_DATA_DIR -- is one setting shown twice, not two.

    Opens itself when the first directory is unset, which is the case worth interrupting
    for; editing any field writes os.environ and drops the loader caches.
    """
    dir_vars = list(dir_vars)
    first_unset = not os.environ.get(dir_vars[0], "").strip() if dir_vars else False

    from loader import clear_cache  # here: loader imports config, this module does not

    with st.expander("Paths", expanded=first_unset):
        changed = False
        for col, var in zip(st.columns(len(dir_vars)), dir_vars):
            label = var + (" (optional)" if var in optional else "")
            value = col.text_input(label, value=os.environ.get(var, ""), key=f"dir_{var}")
            if value != os.environ.get(var, ""):
                os.environ[var] = value
                changed = True
        if changed:
            clear_cache()

        # deliberately NO key: keep() re-assigns every session-state key to exempt it from
        # Streamlit's cleanup, and assigning a button's key is not allowed -- the error
        # surfaces when the button is created, so keep()'s own try/except cannot catch it.
        # Without a key the button never enters session_state. Only one page renders per
        # run, so the two pages' buttons never collide.
        if st.button("Reload from disk"):
            clear_cache()
            st.rerun()
