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

#ifndef CLASSLESS_BOTS_H
#define CLASSLESS_BOTS_H

#include "ClasslessWildcard.h"

class Player;

// A Hero driven by mod-playerbots.
//
// Playerbots builds a bot's whole combat brain from its class, and every Hero
// is on the chassis class, so an altbot Hero would fight with the chassis
// class's rotation and none of its own abilities. ClasslessBots gives such a
// bot a `classless` strategy instead: it reads what the Hero actually owns,
// sorts each spell by what it does, and casts from that.
//
// Everything here compiles to nothing on a server without mod-playerbots.
namespace ClasslessBots
{
    enum Role : uint8
    {
        ROLE_NONE   = 0,
        ROLE_TANK   = 1,
        ROLE_HEAL   = 2,
        ROLE_MELEE  = 3,
        ROLE_RANGED = 4,
    };

    // Adds the strategies, actions and values to playerbots. Call once at
    // startup, after playerbots has built its own (World OnStartup is).
    void Register();

    // Keeps a Hero bot on its classless strategies. Playerbots puts the
    // chassis class's defaults back on every group invite, duel and
    // battleground, so this runs on the 2-second player tick, does nothing
    // for a player without a bot AI, and changes nothing while all is in place.
    void Tick(Player* player, ClasslessWildcard::CharState& st);
}

#endif
