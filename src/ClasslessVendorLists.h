/*
 * mod-classless-wildcard -- vendor list layout (GENERATED)
 *
 * Do not hand-edit: regenerate with
 * data/sql/generators/gen_vendor_lists.py, which writes this header and
 * data/sql/db-world/cw_world_vendor_lists.sql from one description of the
 * shop, so the gossip menu and the npc_vendor rows cannot disagree.
 */

#ifndef MOD_CLASSLESS_VENDOR_LISTS_H
#define MOD_CLASSLESS_VENDOR_LISTS_H

#include <cstdint>

namespace ClasslessWildcard
{
    struct VendorList
    {
        uint32_t    entry;    // npc_vendor.entry
        uint8_t     category; // index into VENDOR_CATEGORIES
        char const* label;
        uint32_t    count;    // items in the list, for the menu text
        bool        whole;    // the category's everything-at-once list
    };

    struct VendorCategory
    {
        char const* name;
        char const* blurb;
    };

    constexpr VendorCategory VENDOR_CATEGORIES[] =
    {
        { "Weapons", "every blade, bow, staff and wand" },
        { "Armor", "chest, legs, shoulders, cloaks and shields" },
        { "Jewelry & off-hand", "necks, rings, trinkets and held items" },
        { "Heirlooms", "bought once, they scale with you to 80" },
    };

    constexpr VendorList VENDOR_LISTS[] =
    {
        { 990110, 0, "Levels 1-20", 30, false },
        { 990111, 0, "Levels 21-40", 32, false },
        { 990112, 0, "Levels 41-60", 20, false },
        { 990113, 0, "Levels 61-80", 20, false },
        { 990114, 0, "All levels", 102, true },
        { 990120, 1, "Levels 1-20", 36, false },
        { 990121, 1, "Levels 21-40", 34, false },
        { 990122, 1, "Levels 41-60", 24, false },
        { 990123, 1, "Levels 61-80", 24, false },
        { 990124, 1, "All levels", 118, true },
        { 990130, 2, "Levels 1-20", 12, false },
        { 990131, 2, "Levels 21-40", 14, false },
        { 990132, 2, "Levels 41-60", 8, false },
        { 990133, 2, "Levels 61-80", 8, false },
        { 990134, 2, "All levels", 42, true },
        { 990144, 3, "Heirlooms", 23, true },
    };

    // The supplies counter is the creature's own list, which
    // SendListInventory reaches with a vendor entry of 0.
    constexpr uint32_t VENDOR_LIST_SUPPLIES = 0;
}

#endif // MOD_CLASSLESS_VENDOR_LISTS_H
