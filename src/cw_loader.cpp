/*
 * mod-classless-wildcard
 * Released under GNU AGPL v3, like AzerothCore.
 */

// From the module's script files
void AddClasslessPlayerScripts();
void AddClasslessNpcScripts();
void AddClasslessCommandScripts();
void AddClasslessAddonScripts();

// Loader entry point — name must match the module folder
// ("mod-classless-wildcard" -> Addmod_classless_wildcardScripts).
void Addmod_classless_wildcardScripts()
{
    AddClasslessPlayerScripts();
    AddClasslessNpcScripts();
    AddClasslessCommandScripts();
    AddClasslessAddonScripts();
}
