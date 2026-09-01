/*
 * mod-classless-wildcard
 * Copyright (C) 2026 Dustin Hendrickson
 *
 * This program is free software; you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation; either version 2 of the License, or
 * (at your option) any later version.
 *
 * This program is distributed in the hope that it will be useful, but
 * WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU
 * General Public License for more details.
 */

// From the module's script files
void AddClasslessPlayerScripts();
void AddClasslessNpcScripts();
void AddClasslessCommandScripts();
void AddClasslessAddonScripts();
void AddClasslessLootScripts();

// Loader entry point — name must match the module folder
// ("mod-classless-wildcard" -> Addmod_classless_wildcardScripts).
void Addmod_classless_wildcardScripts()
{
    AddClasslessPlayerScripts();
    AddClasslessNpcScripts();
    AddClasslessCommandScripts();
    AddClasslessAddonScripts();
    AddClasslessLootScripts();
}
