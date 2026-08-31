"""Make the character-creation screen read as classless.

The server offers one class per race (the Warrior shell, shown as "Hero"), so
the creation screen already displays a single class button. This appends a small
hook to CharacterCreate.lua that hides that leftover button entirely, leaving the
Hero name and description, so the screen looks intentionally classless rather
than like a game with exactly one class.

Append-only: the client's own CharacterCreate.lua is passed through byte for
byte and the hook is added at the end, wrapping CharacterCreateEnumerateClasses
so the buttons are hidden after the original code has set everything up. Class
selection is separate state (SetCharacterClass, driven by GetSelectedClass), so
hiding the buttons does not affect character validity.

This is loaded only because the exe "allow custom interface" patch is applied
with --creation-text; without it the client would reject the modified file.
"""

from __future__ import annotations

_HOOK = """

-- ============================================================
-- mod-classless-wildcard: single-class ("Hero") creation screen
-- Hides the leftover class-selection button. There is only one
-- class, so the picker is noise; the Hero name and description
-- stay. Selection state is untouched (SetCharacterClass still
-- runs via GetSelectedClass), so Accept works normally.
-- ============================================================
if not ClasslessWildcard_HideClass then
    ClasslessWildcard_HideClass = true;
    local _cw_orig_enumerate = CharacterCreateEnumerateClasses;
    function CharacterCreateEnumerateClasses(...)
        _cw_orig_enumerate(...);
        local maxc = MAX_CLASSES_PER_RACE or 10;
        for i = 1, maxc do
            local b = _G["CharacterCreateClassButton"..i];
            if b then b:Hide(); end
        end
    end
end
"""


def add_hide_class_hook(lua_text: str) -> str:
    """Append the class-button hide hook to CharacterCreate.lua.

    Idempotent: if the marker is already present the text is returned unchanged.
    """
    if "ClasslessWildcard_HideClass" in lua_text:
        return lua_text
    if not lua_text.endswith("\n"):
        lua_text += "\n"
    return lua_text + _HOOK
