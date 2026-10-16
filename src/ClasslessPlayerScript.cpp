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

#include "Chat.h"
#include "ConditionMgr.h"
#include "ClasslessBots.h"
#include "ClasslessMgr.h"
#include "Containers.h"
#include "DBCStores.h"
#include "DatabaseEnv.h"
#include "Duration.h"
#include "GossipDef.h"
#include "GameTime.h"
#include "Item.h"
#include "ObjectMgr.h"
#include "Optional.h"
#include "Pet.h"
#include <algorithm>
#include <mutex>
#include <vector>
#include "Player.h"
#include "ScriptMgr.h"
#include "SpellAuraEffects.h"
#include "SpellDefines.h"   // SPELLVALUE_BASE_POINT0
#include "SpellMgr.h"
#include "SpellScript.h"
#include "StringFormat.h"
#include "World.h"

using namespace ClasslessWildcard;

class ClasslessWorldScript : public WorldScript
{
public:
    ClasslessWorldScript() : WorldScript("ClasslessWorldScript", {
        WORLDHOOK_ON_BEFORE_CONFIG_LOAD,
        WORLDHOOK_ON_STARTUP
    }) { }

    void OnBeforeConfigLoad(bool reload) override
    {
        sClasslessMgr->LoadConfig(reload);
    }

    void OnStartup() override
    {
        sClasslessMgr->BuildLibrary();
        ClasslessBots::Register();
    }
};

// The feral attack power the core gives a druid's weapons (Player::_ApplyItemMods:
// from the weapon's DPS, an heirloom's from its scaling at this level). The core
// stores it in m_baseFeralAP, which only its druid melee formula reads, and the
// Paladin chassis never reaches that formula.
static int32 CW_FeralWeaponAP(Player* player)
{
    int32 total = 0;
    for (uint8 slot : { uint8(EQUIPMENT_SLOT_MAINHAND), uint8(EQUIPMENT_SLOT_OFFHAND) })
    {
        Item* item = player->GetItemByPos(INVENTORY_SLOT_BAG_0, slot);
        if (!item || item->IsBroken())
            continue;
        ItemTemplate const* proto = item->GetTemplate();
        int32 dpsMod = 0;
        int32 bonus = 0;
        if (proto->ScalingStatValue)
        {
            ScalingStatDistributionEntry const* ssd = proto->ScalingStatDistribution
                ? sScalingStatDistributionStore.LookupEntry(proto->ScalingStatDistribution) : nullptr;
            uint32 level = player->GetLevel();
            if (ssd && level > ssd->MaxLevel)
                level = ssd->MaxLevel;
            if (ScalingStatValuesEntry const* ssv = sScalingStatValuesStore.LookupEntry(level))
            {
                dpsMod = ssv->getDPSMod(proto->ScalingStatValue);
                bonus += ssv->getFeralBonus(proto->ScalingStatValue);
            }
        }
        total += bonus + proto->getFeralBonus(dpsMod);
    }
    return total;
}

// The pets a Hero has put away, as the core keeps them: one list
// (PetStable::UnslottedPets, PET_SAVE_NOT_IN_SLOT) for a dismissed beast AND
// every demon, ghoul and water elemental a summon replaced. A Hunter never has
// a demon and a Warlock never has a beast, so the core reads that list as one
// or the other, and for a Hero it is both:
//   - Call Pet and Revive Pet with no beast out take the list's FIRST entry
//     (Pet::GetLoadPetInfo), the oldest pet, so they brought back an Imp;
//   - the Stable Master stables or unstables only when the list holds exactly
//     one beast (WorldSession::HandleStablePet, HandleUnstablePet), so a Hero
//     with a demon in it could not get a stabled beast back;
//   - Tame Beast's "you already have a pet" test (GetUnslottedHunterPet) is
//     also a size-one test, so it let a Hero tame without limit.
// So only beasts stay in it. A summon pet that is put away is deleted, and its
// spell summons a new one next time, as for a first summon.
static void CW_PruneUnslottedPets(Player* player)
{
    PetStable* stable = player->GetPetStable();
    if (!stable)
        return;
    std::vector<PetStable::PetInfo>& list = stable->UnslottedPets;
    for (auto it = list.begin(); it != list.end();)
    {
        if (it->Type == HUNTER_PET)
        {
            ++it;
            continue;
        }
        Pet::DeleteFromDB(it->PetNumber);
        it = list.erase(it);
    }
}

class ClasslessPlayerScript : public PlayerScript
{
    // The last money a character SPENT, and the world tick it happened on.
    // A class trainer takes the gold and then teaches the spell, and the
    // module takes the spell straight back -- so without this the Hero pays
    // for nothing. Keyed on the tick because the two happen inside one
    // opcode: a debit from any other source is a different tick.
    struct Spend { uint32 copper = 0; uint32 tick = 0; };
    // Guarded for the same reason _states is: maps update on their own threads
    // and this is one container shared by all of them. Cold enough -- a money
    // change, not a tick -- that a plain lock costs nothing worth measuring.
    std::mutex _lastSpendLock;
    std::unordered_map<uint64, Spend> _lastSpend;

public:
    ClasslessPlayerScript() : PlayerScript("ClasslessPlayerScript", {
        PLAYERHOOK_ON_CREATE,
        PLAYERHOOK_ON_FIRST_LOGIN,
        PLAYERHOOK_ON_LOGIN,
        PLAYERHOOK_ON_LOGOUT,
        PLAYERHOOK_ON_DELETE_FROM_DB,
        PLAYERHOOK_ON_LEVEL_CHANGED,
        PLAYERHOOK_ON_GIVE_EXP,
        PLAYERHOOK_ON_CALCULATE_TALENTS_POINTS,
        PLAYERHOOK_CAN_LEARN_TALENT,
        PLAYERHOOK_ON_LEARN_SPELL,
        PLAYERHOOK_ON_MONEY_CHANGED,
        PLAYERHOOK_ON_AFTER_UPDATE_MAX_POWER,
        PLAYERHOOK_ON_PLAYER_IS_CLASS,
        PLAYERHOOK_ON_PLAYER_HAS_ACTIVE_POWER_TYPE,
        PLAYERHOOK_ON_BEFORE_GUARDIAN_INIT_STATS_FOR_LEVEL,
        PLAYERHOOK_ON_UPDATE,
        PLAYERHOOK_ON_SPELL_CAST,
        PLAYERHOOK_ON_AFTER_SET_VISIBLE_ITEM_SLOT,  // Auto Shot follows the ranged slot
        PLAYERHOOK_CAN_CAST_ITEM_COMBAT_SPELL       // sees every swing's result: a dodge opens Overpower
    }) { }

    // A cooldown the client holds short of the server's, for two reasons.
    //
    // A rune-power spell: Death Grip lit up again within seconds of being
    // cast, and every press after that was refused by the server with "Spell
    // is not ready" for the rest of its 35 seconds. It is the same client rune
    // bookkeeping that is Death Knight only, below.
    //
    // And every spell whose cooldown a talent anywhere could shorten. The
    // client cannot apply a cross-class talent to its own cooldown sweep, so
    // the client patch lowers its copy to the shortest any build could reach
    // (lower_talent_reduced_cooldowns), letting a Hero WITH the talent cast the
    // moment the server agrees. A Hero without it was left with the floor:
    // Revenge's 5 seconds read 1 on the client, the button lit up after one
    // second, and every press for four more was refused.
    //
    // So say it outright. SMSG_SPELL_COOLDOWN is the core's own way of telling
    // the client a cooldown it would not work out for itself, and the client
    // honours it for any class. Sent a tick after the cast so it lands behind
    // SMSG_SPELL_GO, with what the server actually holds, so a talent that
    // shortens the cooldown is already counted. Every Hero cast with a
    // cooldown, not only the floored ones: where the two already agree it
    // changes nothing, and a list of which rows the patch lowered would be one
    // more thing to fall out of step with the client.
    //
    // And the cooldown it SHARES. The shocks are one category: Frost Shock
    // puts Earth and Flame Shock on its 6 seconds too, and the client takes
    // that from its own lowered copy (3 seconds), so they lit up early just
    // the same. The core gives every same-family spell in the category the
    // cooldown (Player::AddSpellAndCategoryCooldowns); each one the Hero
    // knows goes out in the same packet with what the server holds for it.
    void OnPlayerSpellCast(Player* player, Spell* spell, bool /*skipCheck*/) override
    {
        if (!sClasslessMgr->cfg.enabled || !player || !spell || spell->IsTriggered())
            return;
        SpellInfo const* info = spell->GetSpellInfo();
        if (!info)
            return;
        // One Overpower per dodge, as the stock combo point gave: casting it
        // closes the window the dodge opened.
        {
            auto const& overpowers = sClasslessMgr->OverpowerSpells();
            if (std::find(overpowers.begin(), overpowers.end(), info->Id) != overpowers.end())
                sClasslessMgr->CloseOverpowerWindow(player);
        }
        if (!info->RecoveryTime && !info->CategoryRecoveryTime)
            return;
        CharState* st = sClasslessMgr->FindState(player);
        if (!st || st->exempt)
            return;
        if (info->PowerType == POWER_RUNE
            && (player->getClass() == CLASS_DEATH_KNIGHT || !st->runes))
            return;   // a real Death Knight's client tracks these itself

        uint32 const spellId = info->Id;
        uint32 const category = info->CategoryRecoveryTime ? info->GetCategory() : 0;
        uint32 const family = info->SpellFamilyName;
        player->m_Events.AddEventAtOffset([player, spellId, category, family]()
        {
            PacketCooldowns cooldowns;
            if (uint32 const left = player->GetSpellCooldownDelay(spellId))
                cooldowns[spellId] = left;
            if (category)
            {
                auto const set = sSpellsByCategoryStore.find(category);
                if (set != sSpellsByCategoryStore.end())
                    for (auto const& [fromItem, otherId] : set->second)
                    {
                        if (fromItem || otherId == spellId || !player->HasSpell(otherId))
                            continue;
                        SpellInfo const* other = sSpellMgr->GetSpellInfo(otherId);
                        if (!other || other->SpellFamilyName != family)
                            continue;
                        if (uint32 const left = player->GetSpellCooldownDelay(otherId))
                            cooldowns[otherId] = left;
                    }
            }
            if (cooldowns.empty())
                return;
            WorldPacket data;
            player->BuildCooldownPacket(data, SPELL_COOLDOWN_FLAG_NONE, cooldowns);
            player->SendDirectMessage(&data);
        }, 1ms);
    }

    // Runs before the money actually moves, with the signed delta.
    void OnPlayerMoneyChanged(Player* player, int32& amount) override
    {
        if (!sClasslessMgr->cfg.enabled || amount >= 0)
            return;
        std::lock_guard<std::mutex> spendGuard(_lastSpendLock);
        Spend& spend = _lastSpend[player->GetGUID().GetCounter()];
        spend.copper = uint32(-amount);
        spend.tick = uint32(GameTime::GetGameTimeMS().count());
    }

    // "Does this Hero count as a <class> for the purposes of X?"
    //
    // The core asks this wherever behaviour is class-specific, tagging each
    // question with a ClassContext. Every Hero runs one chassis (Paladin by
    // default), so without an answer here the chassis quietly decides what a
    // classless character may do -- a Hero could equip a Libram but never an
    // Idol, Totem or Sigil, however much druid or shaman a build had bought.
    //
    // Answered only for the contexts where the chassis would otherwise take
    // something away. std::nullopt everywhere else means "use my real class",
    // deliberately: the untouched contexts drive Death Knight rune machinery
    // and the stat/talent maths this module already replaces, where claiming
    // to be every class at once breaks things rather than freeing them.
    // Counterattack is the only thing AURA_STATE_HUNTER_PARRY feeds, so a
    // Hero is a hunter for the parry question exactly when they hold it.
    // Ranks, oldest first; HasSpell is a hash lookup and this runs only on a
    // parry.
    static bool IsDruidForm(ShapeshiftForm form)
    {
        switch (form)
        {
            case FORM_CAT:
            case FORM_TREE:
            case FORM_TRAVEL:
            case FORM_AQUA:
            case FORM_BEAR:
            case FORM_DIREBEAR:
            case FORM_FLIGHT_EPIC:
            case FORM_FLIGHT:
            case FORM_MOONKIN:
                return true;
            default:
                return false;
        }
    }

    static bool OwnsCounterattack(Player const* player)
    {
        static constexpr uint32 COUNTERATTACK_RANKS[] =
            { 19306, 20909, 20910, 27067, 48998, 48999 };
        for (uint32 id : COUNTERATTACK_RANKS)
            if (player->HasSpell(id))
                return true;
        return false;
    }

    // Does this character have that power at all?
    //
    // The core asks this before every rage grant there is, and its own answer
    // is `getPowerType() == power` -- the bar on screen. A Hero has mana, rage
    // and energy at once and shows one of them, so the honest answer for all
    // three is yes, and the five rage paths this module cannot hook (damage
    // taken, absorbed damage, block, dodge and parry, and EffectEnergize for
    // every rage-granting spell in the game) start working.
    //
    // Returning false is not "no": it hands the question back to the core,
    // whose answer is the displayed bar.
    //
    // Nothing is asked of the character's state until it is in the world.
    // Player::Create asks this while building a brand new character, and the
    // state is loaded with database queries -- so before then the core's own
    // answer stands, which is what it was doing anyway.
    bool OnPlayerHasActivePowerType(Player const* player, Powers power) override
    {
        if (!sClasslessMgr->cfg.enabled || !player || !player->IsInWorld())
            return false;
        // bots and system accounts keep vanilla resource rules. In the world
        // the state is already loaded, so this is a map lookup.
        if (sClasslessMgr->IsExempt(const_cast<Player*>(player)))
            return false;

        switch (power)
        {
            // the three UniversalResources gives every Hero a real maximum in
            case POWER_MANA:
            case POWER_RAGE:
            case POWER_ENERGY:
                return true;
            // Runes are per character and opt-in, so this one is read rather
            // than assumed.
            case POWER_RUNIC_POWER:
                return sClasslessMgr->GetState(const_cast<Player*>(player)).runes;
            default:
                return false;
        }
    }

    Optional<bool> OnPlayerIsClass(Player const* player, Classes playerClass, ClassContext context) override
    {
        Config const& cfg = sClasslessMgr->cfg;
        if (!cfg.enabled)
            return std::nullopt;

        // Decide on the context BEFORE looking the character up. IsClass runs
        // in combat paths and during login, and the state lookup can pull a
        // character in from the database; every context we do not answer must
        // cost nothing but this switch.
        switch (context)
        {
            // Relics: Libram, Idol, Totem, Sigil and the warlock relic all
            // live in slot 17, but the core hands that slot out only to the
            // one class each belongs to -- in FindEquipSlot and again in
            // CanUseItem. A Hero should be able to wear whichever matches the
            // spells they actually bought.
            case CLASS_CONTEXT_EQUIP_RELIC:
            // Shields are restricted to Paladin/Warrior/Shaman. The default
            // chassis already passes that test, but a realm configured onto
            // any other chassis would silently lose shields.
            case CLASS_CONTEXT_EQUIP_SHIELDS:
            // Reactive abilities -- Overpower, Revenge, Riposte, Counterattack
            // -- light up only when the core sets the matching aura state, and
            // this is the ONE context where "a Hero is every class" is the
            // wrong answer, because the core uses these questions to choose
            // BETWEEN states that exclude each other:
            //
            //   dodge  Unit.cpp: `if (!IsClass(CLASS_ROGUE, ...))` sets
            //          AURA_STATE_DEFENSE. Answering yes skipped it, so
            //          Revenge never came up after a dodge.
            //   parry  `if (IsClass(CLASS_HUNTER, ...))` sets HUNTER_PARRY,
            //          else DEFENSE. Answering yes took the hunter branch, so
            //          Revenge never came up after a parry either.
            //   block  unconditional, which is why blocks worked and were the
            //          only thing that did.
            //
            //   dodge, as the ATTACKER
            //          `if (IsClass(CLASS_WARRIOR, ...))` grants a combo point
            //          and starts REACTIVE_OVERPOWER; its expiry, and
            //          ClearAllReactives, call ClearComboPoints(). That is how
            //          "only useable after a dodge" is built, and answering yes
            //          handed both halves to every Hero -- a free Overpower to
            //          anyone carrying rogue combo points, and a wipe of those
            //          points five seconds after any dodge.
            //
            // So answer from what the Hero actually owns. A Hero holding
            // Counterattack is a hunter for the parry question and gets
            // HUNTER_PARRY; everyone else gets DEFENSE and Revenge works. No
            // Hero is a warrior for the dodge question: Overpower waits on an
            // aura state of its own (see the warrior branch below), so combo
            // points belong to whatever builds them.
            // Nobody is a rogue here: the rogue answer exists only to DENY
            // the defense state on a dodge, and Riposte reads that same state,
            // so saying no costs a Riposte holder nothing and hands Revenge
            // back to everyone.
            case CLASS_CONTEXT_ABILITY_REACTIVE:
                if (playerClass == CLASS_ROGUE)
                    return false;
                if (playerClass == CLASS_HUNTER)
                {
                    if (sClasslessMgr->IsExempt(const_cast<Player*>(player)))
                        return std::nullopt;
                    return OwnsCounterattack(player);
                }
                if (playerClass == CLASS_WARRIOR)
                {
                    // Overpower no longer runs on combo points (see
                    // ClasslessMgr::GateOverpowerOnDodge); it waits on an aura
                    // state of its own. The core asks this question in three
                    // places: when a target dodges the player, when its
                    // Overpower timer runs out, and in ClearAllReactives (death
                    // and a dual-spec switch). The timer never starts, because
                    // the answer is no, so only the other two reach here. Death
                    // has already set the dead state when it asks, so a living
                    // player not mid-teleport is the dodge; a dead one closes
                    // the window.
                    //
                    // Not "in combat": the combat manager never puts a game
                    // master with .gm on into combat, and requiring it closed
                    // the window on every dodge a GM landed. A spec switch can
                    // open a five-second window out of combat, which costs
                    // nothing.
                    //
                    // This is the signal for a dodged special attack. A dodged
                    // swing also arrives through OnPlayerCanCastItemCombatSpell
                    // below, which does not depend on this module being the
                    // one that answers the class question.
                    Player* self = const_cast<Player*>(player);
                    if (sClasslessMgr->OwnsOverpower(player))
                    {
                        if (player->IsAlive() && player->GetHealth() > 0 && !player->IsBeingTeleported())
                            sClasslessMgr->OpenOverpowerWindow(self);
                        else
                            sClasslessMgr->CloseOverpowerWindow(self);
                    }
                    // No combo point and no combo-point wipe for a Hero, so a
                    // rogue or cat build's points are its own. A real warrior
                    // (an exempt account) keeps the core's answer; its combo
                    // point is harmless now that Overpower does not read it.
                    if (sClasslessMgr->IsExempt(self))
                        return std::nullopt;
                    return false;
                }
                break;
            // Stats are the chassis's, deliberately: the module adds its own
            // attack and spell power on top and the addon quotes the chassis
            // rates, so a blanket answer here would rewrite formulas it has
            // already accounted for. Druid is the one exception worth making,
            // and only for the three sites that ask it:
            //
            //   Player.cpp    the feral attack power carried on a WEAPON. The
            //                 core stores it, but only its druid melee formula
            //                 reads it, and that is unreachable (below), so the
            //                 universal stat layer adds it in a feral form
            //                 (CW_FeralWeaponAP).
            //   StatSystem    ranged attack power, which the druid branch puts
            //                 at zero in a feral form and leaves at Agility-10
            //                 outside one -- the same as the default branch.
            //   StatSystem    melee attack power, which is UNREACHABLE: the
            //                 chain tests Paladin, Death Knight and Warrior,
            //                 then Hunter, Shaman and Rogue, before it ever
            //                 reaches druid.
            //
            // That last one is what makes this safe, and it is safe only while
            // the chassis is one of those six. A realm on a Mage or Priest
            // chassis would fall through to the druid formula and have its
            // melee attack power rewritten, so the answer is withheld there.
            case CLASS_CONTEXT_STATS:
                // Every class but druid keeps the chassis's own answer. A
                // `break` here would fall through to the yes below and make a
                // Hero every class at once for the attack and spell power
                // formulas, which is the whole thing this case exists to avoid.
                if (playerClass != CLASS_DRUID)
                    return std::nullopt;
                switch (player->getClass())
                {
                    case CLASS_PALADIN:
                    case CLASS_DEATH_KNIGHT:
                    case CLASS_WARRIOR:
                    case CLASS_HUNTER:
                    case CLASS_SHAMAN:
                    case CLASS_ROGUE:
                        break;                 // the melee chain stops first
                    default:
                        return std::nullopt;   // it would not, so say nothing
                }
                break;
            // Class quests are open to every Hero in the database, but a few
            // chains gate a scripted STEP in C++ as well, where no SQL can
            // reach: the Moonglade gossip that hands out the druid's aquatic
            // form quest, and the Death Knight duel quest. Without an answer
            // here a Hero can accept a chain the module opened and then find
            // the NPC that finishes it will not talk.
            case CLASS_CONTEXT_QUEST:
            // The same gossip's free flight to Moonglade, and the Acherus
            // taxi's mount fix, which is guarded on the node id so it reaches
            // nothing else.
            case CLASS_CONTEXT_TAXI:
            // Enslave Demon. The core hands a charmed DEMON to CharmAI and
            // fixes up the class byte the client reads only when the charmer
            // is a warlock; a Hero's enslaved demon kept its creature AI
            // instead. Both branches are already guarded on the creature
            // being a demon, so there is nothing else this can touch.
            case CLASS_CONTEXT_PET_CHARM:
                break;
            // Runes, and only the Death Knight question, and only when Death
            // Knight content is switched on.
            //
            // Three sites share this context for CLASS_DEATH_KNIGHT and they
            // must agree: Player::InitRunes allocates m_runes, Player::Update
            // ticks rune cooldowns through it, and Regenerate(RUNIC_POWER)
            // refills the bar. The rune accessors dereference m_runes with no
            // null check, so answering some and not others would allocate
            // nothing and then read it. Answering none -- which is where this
            // module stood -- is self-consistent but leaves a Hero who has
            // bought a rune-cost spell casting into a null rune block.
            //
            // Tied to IncludeDeathKnight so a realm that does not use Death
            // Knight abilities pays neither the allocation nor the per-tick
            // rune loop.
            // This context is not only the rune question. LootHandler asks it
            // three times as `IsClass(CLASS_ROGUE, CLASS_CONTEXT_ABILITY)`
            // before it will let anyone pick a pocket, which is why a Hero was
            // told they had no permission to loot. The other uses are all safe
            // to answer yes to: the shaman one scales a weapon totem enchant,
            // the paladin one removes Righteous Fury on a spec switch, and the
            // priest one is gated again on actually holding Spirit of
            // Redemption. Only the Death Knight answer has to stay conditional.
            case CLASS_CONTEXT_ABILITY:
                // The druid question is asked in two places, both about a form
                // changing: leaving the last form clears snares and roots, and
                // a shift recalculates Dash and redoes disarm. Those are druid
                // form rules, so the answer is whether the form being entered
                // or left IS a druid form. A flat yes cleared snares whenever a
                // Hero left Stealth, Shadowform or Ghost Wolf, which no class
                // gets. Swapping stances never reached it either way: the new
                // stance is registered before the old one comes off.
                if (playerClass == CLASS_DRUID)
                {
                    if (sClasslessMgr->IsExempt(const_cast<Player*>(player)))
                        return std::nullopt;
                    CharState const* st = sClasslessMgr->FindState(const_cast<Player*>(player));
                    return IsDruidForm(player->GetShapeshiftForm())
                        || (st && IsDruidForm(ShapeshiftForm(st->heldForm)));
                }
                if (playerClass != CLASS_DEATH_KNIGHT)
                    break;
                // Exempt characters (bots) keep their real class. CharState::runes
                // is false for every one of them, so answering from it skipped
                // InitRunes for a real Death Knight, and anything that reads its
                // runes (the playerbots AI does, every tick) read a null block.
                if (sClasslessMgr->IsExempt(const_cast<Player*>(player)))
                    return std::nullopt;
                // From the character's own snapshot, NOT the live config: this
                // same question gates both the one-time InitRunes allocation
                // and the per-tick loop that reads the block it allocates. If
                // a `.reload config` could change the answer underneath a
                // logged-in character, the loop would read a block InitRunes
                // never made.
                return sClasslessMgr->GetState(const_cast<Player*>(player)).runes;
            // Pets. Answered from the pet the Hero actually has, not from the
            // class alone, because two call sites need opposite answers.
            //
            // Pet::IsPermanentPetFor runs an if/else chain -- warlock, then
            // death knight, then mage -- and permanence decides the pet
            // spellbook, the pet tab and whether owner auras reach it. A flat
            // "yes" to warlock wins that chain every time and answers
            // "is it a demon?" for a ghoul, so a ghoul could never be
            // permanent. Answering per class from the pet's creature type lets
            // the core's own chain fall through to the right branch.
            //
            // Meanwhile LoadPetFromDB bails out on
            //   IsClass(DEATH_KNIGHT, PET) && !CanSeeDKPet()
            // and CanSeeDKPet is the Master of Ghouls flag no Hero has, so
            // claiming death knight there would stop pets loading from the
            // database at all. That call happens while the pet is being
            // restored and the Hero therefore has none, so returning nullopt
            // when there is no pet keeps that path on the real class -- the
            // hazard is closed by construction rather than by remembering.
            // The questions asked with no context. The only Paladin ones are the
            // halved heal threat (Spell.cpp direct heals, SpellAuraEffects.cpp
            // heal-over-time ticks and leech): every Hero is a Paladin, so every
            // Hero's heals drew half threat. A Hero is answered "no" and heals
            // for the normal amount. Any other class asked here is the core's.
            case CLASS_CONTEXT_NONE:
                if (playerClass != CLASS_PALADIN)
                    return std::nullopt;
                if (sClasslessMgr->IsExempt(const_cast<Player*>(player)))
                    return std::nullopt;
                return false;
            case CLASS_CONTEXT_PET:
            {
                // answers inline below, so it checks the exemption itself
                if (sClasslessMgr->IsExempt(const_cast<Player*>(player)))
                    return std::nullopt;
                Pet* pet = player->GetPet();
                // With no pet there is nothing to read a type from, and this is
                // exactly when taming asks: Spell::EffectTameCreature and
                // EffectCreateTamedPet both check before the pet exists.
                // Falling through to the chassis meant the tame finished and
                // silently produced nothing. A Hero may keep any class's pet,
                // so with none the answer is yes.
                if (!pet || !pet->GetCreatureTemplate())
                    return true;
                uint32 const creatureType = pet->GetCreatureTemplate()->type;
                switch (playerClass)
                {
                    case CLASS_WARLOCK:      return creatureType == CREATURE_TYPE_DEMON;
                    case CLASS_DEATH_KNIGHT: return creatureType == CREATURE_TYPE_UNDEAD;
                    case CLASS_MAGE:         return creatureType == CREATURE_TYPE_ELEMENTAL;
                    case CLASS_HUNTER:       return creatureType == CREATURE_TYPE_BEAST;
                    default:                 return std::nullopt;
                }
            }
            default:
                // A wand shot takes the wand's own damage school (see
                // IsWandSchoolContext). Every Hero is a wand user, so this
                // joins the yes below; a core without the context never asks.
                if (IsWandSchoolContext(context))
                    break;
                return std::nullopt;
        }

        // bots and system accounts play by vanilla class rules
        if (sClasslessMgr->IsExempt(const_cast<Player*>(player)))
            return std::nullopt;

        return true;
    }

    // What KIND of pet is this?
    //
    // Pet::Create works it out from the owner's class, so on a one-chassis
    // realm it worked it out as "none": petType stayed MAX_PET_TYPE, the core
    // logged "Unknown type pet ... summoned by player class 2" on every
    // summon, the pet never got UNIT_FLAG_PLAYER_CONTROLLED (no dismiss
    // prompt), and it was not recorded as the player's current pet. The pet
    // still appeared and still took orders, which is why it looks fine.
    //
    // This hook takes petType by reference and runs before that guess, so
    // decide from the pet instead of from the owner: hunters tame beasts,
    // every other pet a class summons -- demon, undead, elemental -- is a
    // summoned pet. Setting it here also skips the class chain entirely, so a
    // tamed beast cannot be mistyped as a summon.
    void OnPlayerBeforeGuardianInitStatsForLevel(Player* player, Guardian* guardian,
                                                 CreatureTemplate const* cinfo, PetType& petType) override
    {
        Config const& cfg = sClasslessMgr->cfg;
        if (!cfg.enabled || !player || !guardian || !cinfo)
            return;
        if (sClasslessMgr->IsExempt(player))
            return;
        if (!guardian->IsPet())
            return;

        petType = (cinfo->type == CREATURE_TYPE_BEAST) ? HUNTER_PET : SUMMON_PET;
    }

    // Universal resources: every Hero keeps mana, rage AND energy pools alive
    // simultaneously (the client already tracks all pools — druids prove it —
    // only the chassis bar is displayed; the addon renders the off-pools).
    // This hook fires at the end of Player::UpdateMaxPower for every power
    // type on every stat update, so the pools can never be zeroed out.
    void OnPlayerAfterUpdateMaxPower(Player* player, Powers& power, float& value) override
    {
        Config const& cfg = sClasslessMgr->cfg;
        if (!cfg.enabled)
            return;
        if (sClasslessMgr->IsExempt(player)) // bots/system accounts stay vanilla
            return;

        switch (power)
        {
            case POWER_RAGE:
                value = std::max(value, float(cfg.urMaxRage));
                break;
            case POWER_ENERGY:
                value = std::max(value, float(cfg.urMaxEnergy));
                break;
            default:
                break;
        }
    }

    // Put the character on the one chassis the moment it is created, so the
    // character list, its starting stats and its saved class all agree from
    // the very first byte written.
    void OnPlayerCreate(Player* player) override
    {
        if (sClasslessMgr->cfg.enabled)
        {
            sClasslessMgr->EnforceChassis(player);
            // Dress the Hero in the neutral outfit now, so the character-select
            // screen shows it instead of the shell class's starting gear. This
            // hook fires AFTER creation's SaveToDB already committed, so the
            // gear change must be saved again or it silently evaporates.
            if (sClasslessMgr->ApplyStarterGear(player))
                player->SaveToDB(false, false);
        }
    }

    void OnPlayerFirstLogin(Player* player) override
    {
        if (sClasslessMgr->cfg.enabled)
            sClasslessMgr->HandleFirstLogin(player);
    }

    void OnPlayerLogin(Player* player) override
    {
        Config const& cfg = sClasslessMgr->cfg;
        if (!cfg.enabled)
            return;

        // characters that predate the module, or predate a chassis change,
        // convert here on their next login
        sClasslessMgr->EnforceChassis(player);

        sClasslessMgr->HandleLogin(player);
        sClasslessMgr->SyncArmorWeight(player);

        // InitTalentForLevel hands out (ceiling - used) free points whenever the
        // core recalculates, and it recalculates on login. Spending them is
        // refused by OnPlayerCanLearnTalent, but the number itself should read
        // zero, so take them straight back.
        if (!sClasslessMgr->IsExempt(player))
            player->SetFreeTalentPoints(0);

        // A Hero may keep an undead pet, so let them see one.
        //
        // CanSeeDKPet is the Master of Ghouls flag, and the core leans on it
        // twice: LoadPetFromDB refuses to restore a pet for anyone who counts
        // as a Death Knight without it, and the character-select screen hides
        // a stored ghoul. Since the module answers the Death Knight pet
        // question for a Hero holding an undead pet, leaving the flag off
        // would let that refusal fire while a ghoul is already out and block
        // the next pet from loading. Setting it makes the check moot in the
        // right direction and shows the ghoul on the login screen besides.
        if (!sClasslessMgr->IsExempt(player))
            player->SetShowDKPet(true);

        // Restore the saved main-bar choice once the login stat pass has
        // settled. The chassis owns the mana pool itself -- it is a real class
        // with a real base mana, so there is nothing here to build.
        if (!sClasslessMgr->IsExempt(player))
            player->m_Events.AddEventAtOffset([player]()
            {
                sClasslessMgr->ApplyDisplayPower(player); // saved bar choice
            }, 2s);
    }

    // A deleted character has to take its module rows with it.
    //
    // ObjectMgr::SetHighestGuids sets the player GUID counter to MAX(guid) + 1
    // at EVERY startup, so deleting the highest character and restarting hands
    // that same GUID to the next character created. Without this, that new
    // character would load the deleted Hero's abilities, talents, essence,
    // stat allocation, chosen path and reroll cooldowns -- a fresh level 1 with
    // somebody else's level 80 build -- plus their challenge-run history (the
    // "best" records the picker shows and the finish payout checks) and
    // Nemesis marks. Even where the GUID is not reused the rows would simply
    // accumulate forever.
    //
    // Appended to the core's own delete transaction, so the rows go with the
    // character or not at all.
    void OnPlayerDeleteFromDB(CharacterDatabaseTransaction trans, uint32 guid) override
    {
        trans->Append("DELETE FROM cw_char_state WHERE guid = {}", guid);
        trans->Append("DELETE FROM cw_char_abilities WHERE guid = {}", guid);
        trans->Append("DELETE FROM cw_char_talents WHERE guid = {}", guid);
        trans->Append("DELETE FROM cw_char_bans WHERE guid = {}", guid);
        trans->Append("DELETE FROM cw_char_custom_archetype WHERE guid = {}", guid);
        trans->Append("DELETE FROM cw_char_runs WHERE guid = {}", guid);
        trans->Append("DELETE FROM cw_char_nemeses WHERE guid = {}", guid);
        trans->Append("DELETE FROM cw_char_nemesis_heads WHERE guid = {}", guid);
        trans->Append("DELETE FROM cw_char_nemesis_run WHERE guid = {}", guid);
        trans->Append("DELETE FROM cw_char_nemesis_charm WHERE guid = {}", guid);
        sClasslessMgr->UnloadState(ObjectGuid::Create<HighGuid::Player>(guid));
    }

    void OnPlayerLogout(Player* player) override
    {
        std::lock_guard<std::mutex> spendGuard(_lastSpendLock);
        _lastSpend.erase(player->GetGUID().GetCounter());
        // a hunter with nobody to hunt leaves; before the state goes, which
        // is where its guid lives
        sClasslessMgr->DespawnHunter(player);
        sClasslessMgr->DespawnNemesisCopies(player);
        // Hourglass's and Pursued's clocks run in memory between saves, and
        // nothing else saves at logout: without this a logout put either
        // clock back to whatever the last level-up or death had saved.
        if (sClasslessMgr->FindState(player))
            sClasslessMgr->SaveState(player);
        sClasslessMgr->UnloadState(player->GetGUID());
    }

    // A dodged swing opens Overpower.
    //
    // Player::CastItemCombatSpell runs after every melee swing, dodged or not,
    // and asks this once per equipped item with the swing's hit mask. That is
    // a dodge signal the module owns outright: unlike the class question
    // above, no other module's answer can stand in front of it. Asked once
    // per item, so OpenOverpowerWindow treats repeats in one tick as one.
    // Always lets the item's own spell go ahead.
    bool OnPlayerCanCastItemCombatSpell(Player* player, Unit* /*target*/, WeaponAttackType /*attType*/,
                                        uint32 /*procVictim*/, uint32 procEx, Item* /*item*/,
                                        ItemTemplate const* /*proto*/) override
    {
        if ((procEx & PROC_HIT_DODGE) && sClasslessMgr->cfg.enabled && player->IsAlive()
            && sClasslessMgr->OwnsOverpower(player))
            sClasslessMgr->OpenOverpowerWindow(player);
        return true;
    }

    // Auto Shot follows the ranged slot (ClasslessMgr::SyncAutoShot).
    //
    // SetVisibleItemSlot is the one place both directions pass through:
    // EquipItem calls it with the item and RemoveItem with null, so a swap, an
    // unequip to the bag, a sale or a destroy off the paper doll all land
    // here. Deferred a tick because a swap is a removal followed by an equip,
    // and syncing on each would unlearn and relearn the spell in one frame.
    // Login loads the inventory before the character is in the world; the
    // login grant and sweep cover that case.
    void OnPlayerAfterSetVisibleItemSlot(Player* player, uint8 slot, Item* /*item*/) override
    {
        if (slot != EQUIPMENT_SLOT_RANGED || !sClasslessMgr->cfg.enabled)
            return;
        if (!player->IsInWorld() || player->isBeingLoaded())
            return;
        CharState* st = sClasslessMgr->FindState(player);
        if (!st || st->exempt || st->autoShotSyncPending)
            return;
        st->autoShotSyncPending = true;
        player->m_Events.AddEventAtOffset([player]()
        {
            if (CharState* pending = sClasslessMgr->FindState(player))
                pending->autoShotSyncPending = false;
            sClasslessMgr->SyncAutoShot(player);
        }, 1ms);
    }

    // 2-second maintenance tick:
    //  * universal STAT layer — fills the gaps the chassis math leaves so
    //    every allocatable stat matters on a classless Hero:
    //    AGI -> melee/ranged AP, INT -> spell power.
    //    (STR->AP/block, STA->health, AGI->crit/dodge, INT->mana/spell crit
    //    already work uniformly through the shared chassis.)
    void OnPlayerUpdate(Player* player, uint32 p_time) override
    {
        Config const& cfg = sClasslessMgr->cfg;
        if (!cfg.enabled)
            return;
        if (!player->IsInWorld() || !player->IsAlive())
            return;

        // The stock 3.3.5 client only shows combo points for rogues and cat
        // druids -- Wow.exe gates GetComboPoints by class, so a Hero never SEES
        // the points the server tracks (retail warriors had the same hidden
        // Overpower combo points). Mirror them over the addon channel whenever
        // they change; the addon lights its own pips from this.
        // FindState, not GetState. GetState CREATES the entry when it is
        // missing, and this runs for every player on every map update -- an
        // unordered_map insert on the hottest path in the module, from
        // whichever map thread arrived first. There is nothing to say about a
        // character whose state has not loaded yet, so there is nothing to
        // create either.
        CharState* state = sClasslessMgr->FindState(player);
        if (!state)
            return;

        {
            CharState& cpSt = *state;
            if (!cpSt.exempt)
            {
                // Report points for the CURRENT target only, matching what the
                // client would show: combo points stay attached to the unit
                // they were built on, so selecting another mob (or deselecting)
                // must read as zero rather than leaving stale pips lit.
                Unit* selected = player->GetSelectedUnit();
                uint8 cp = selected ? player->GetComboPoints(selected) : 0;
                if (cp != cpSt.lastComboPush)
                {
                    cpSt.lastComboPush = cp;
                    PushAddon(player, Acore::StringFormat("CP|{}", uint32(cp)));
                }

                // Runes have the same problem, one step worse: the stock UI
                // draws the rune bar only for real Death Knight characters, so
                // a Hero with rune-cost abilities gets no way at all to see
                // which runes are up. Mirror the block over the addon channel
                // and let the addon draw it.
                //
                // Guarded by the character's own snapshot, which is exactly
                // the condition under which InitRunes allocated the block --
                // reading it otherwise would dereference a null pointer.
                //
                // And only for a Hero who has bought something that SPENDS
                // them. Every Hero carries a rune block whether they use it or
                // not, and six pips plus a runic bar is the tallest thing on
                // the resource frame, so drawing it for all of them fills the
                // frame with something most will never spend. Recomputed at
                // most once a second: rolling an ability in or out is rare,
                // and scanning the owned list every tick for every player
                // online is not worth the answer.
                if (cpSt.runes)
                {
                    cpSt.runeOwnAcc += p_time;
                    if (cpSt.lastRuneOwn < 0 || cpSt.runeOwnAcc >= 1000)
                    {
                        cpSt.runeOwnAcc = 0;
                        int8 own = 0;
                        for (auto const& entry : cpSt.abilities)
                        {
                            SpellInfo const* info = sSpellMgr->GetSpellInfo(entry.first);
                            if (info && (info->RuneCostID
                                         || info->PowerType == POWER_RUNIC_POWER))
                            {
                                own = 1;
                                break;
                            }
                        }
                        if (own != cpSt.lastRuneOwn)
                        {
                            cpSt.lastRuneOwn = own;
                            // turning ON: forget what was sent so the next
                            // block below pushes the real state at once.
                            // turning OFF: say so, or the row the addon has
                            // already drawn stays until the next login.
                            cpSt.lastRuneSig = 0xFFFFFFFF;
                            cpSt.lastRunicBucket = 255;
                            if (!own)
                                PushAddon(player, "RU|0|0");
                        }
                    }
                }

                // The client does not bring a spent rune back on its own
                // unless the displayed bar is runic power, which a Hero's
                // never is: it takes the spend from SMSG_SPELL_GO, and only
                // its per-frame check, gated on that bar, marks the rune up
                // again. The client patch lifts that gate (lib/exepatch.py);
                // without it the runes came back only with the next rune
                // spell's SPELL_GO, so spending all six locked every rune
                // spell until a relog. The core sends nothing when a rune
                // comes back ("runes act as cooldowns"), so tell the client
                // each time one does, the way Empower Rune Weapon tells it:
                // that sets the rune's ready time to now, so the patched
                // check picks it up the next frame and the client follows
                // the server rather than its own estimate.
                if (cpSt.runes && player->getClass() != CLASS_DEATH_KNIGHT)
                {
                    uint8 ready = 0;
                    for (uint8 i = 0; i < MAX_RUNES; ++i)
                        if (!player->GetRuneCooldown(i))
                            ready |= uint8(1 << i);
                    uint8 const back = ready & ~cpSt.lastReadyRunes;
                    cpSt.lastReadyRunes = ready;
                    if (back)
                    {
                        WorldPacket data(SMSG_ADD_RUNE_POWER, 4);
                        data << uint32(back);
                        player->SendDirectMessage(&data);
                    }
                }

                if (cpSt.runes && cpSt.lastRuneOwn > 0)
                {
                    // Summarise first, send only if it actually changed. Rune
                    // cooldowns count down every frame, so comparing the
                    // rendered message would send one addon message per tick
                    // for the whole ten seconds a rune takes to come back.
                    // The signature is what the bar SHOWS: rune types and
                    // which are up. Runic power is handled separately below.
                    uint32 maxRunic = player->GetMaxPower(POWER_RUNIC_POWER);
                    uint32 runic = player->GetPower(POWER_RUNIC_POWER);
                    uint32 sig = 0;
                    for (uint8 i = 0; i < MAX_RUNES; ++i)
                    {
                        sig = sig * 8 + uint32(player->GetCurrentRune(i));
                        sig = sig * 2 + (player->GetRuneCooldown(i) ? 0u : 1u);
                    }
                    uint8 bucket = maxRunic ? uint8(runic * 20 / maxRunic) : uint8(0);

                    // A rune changing state is an event and redraws at once.
                    // Runic power moves continuously, so on its own it redraws
                    // at most once a second -- otherwise it, not the runes,
                    // sets the message rate.
                    cpSt.runeAcc += p_time;
                    bool const runesChanged = (sig != cpSt.lastRuneSig);
                    bool const runicDue = (bucket != cpSt.lastRunicBucket) && cpSt.runeAcc >= 1000;

                    if (runesChanged || runicDue)
                    {
                        cpSt.lastRuneSig = sig;
                        cpSt.lastRunicBucket = bucket;
                        cpSt.runeAcc = 0;
                        // "RU|<runic>|<maxRunic>|<type>,<ready>|... x6"
                        std::string msg = Acore::StringFormat("RU|{}|{}", runic, maxRunic);
                        for (uint8 i = 0; i < MAX_RUNES; ++i)
                            msg += Acore::StringFormat("|{},{}",
                                uint32(player->GetCurrentRune(i)),
                                player->GetRuneCooldown(i) ? 0 : 1);
                        PushAddon(player, msg);
                    }
                }
            }
        }

        uint32& acc = state->tickAcc;
        acc += p_time;
        if (acc < 2000)
            return;
        acc %= 2000;

        if (sClasslessMgr->IsExempt(player))
            return;

        // the one FindState above already answered this, and it created
        // nothing to do it
        CharState& st = *state;

        // a Hero playerbots drives fights with its own kit, not its chassis's
        ClasslessBots::Tick(player, st);

        // heavy armor slows casting and attacks; follows gear changes here
        sClasslessMgr->SyncArmorWeight(player);

        // A pet that was away when its spell went is not caught by the sweep in
        // RemoveAbilityInternal: mounting temporarily unsummons it, so a Hero
        // who rerolls Summon Imp while mounted has no pet to send home at that
        // moment and gets the imp back on dismounting. Costs a map lookup and a
        // known-spell check every two seconds.
        sClasslessMgr->DismissOrphanedSummons(player);

        // demons, ghouls and water elementals out of the put-away pet list
        CW_PruneUnslottedPets(player);

        // the trophies and the Nemesis Charm in the bags, as stat changes
        sClasslessMgr->ApplyNemesisFx(player);

        // Player::InitDataForForm resets the displayed power to the CLASS's own
        // whenever a shapeshift starts or ends, and a warrior stance counts --
        // so a Hero who picked the rage bar was put back on mana the first time
        // they used Battle Stance. Cat, Ghoul, Bear and Dire Bear are the forms
        // the core gives a power type of their own; in anything else, including
        // no form at all, the Hero's own choice stands.
        if (st.displayPower != 255)
        {
            switch (player->GetShapeshiftForm())
            {
                case FORM_CAT:
                case FORM_GHOUL:
                case FORM_BEAR:
                case FORM_DIREBEAR:
                    break;
                default:
                    sClasslessMgr->ApplyDisplayPower(player);
                    break;
            }
        }

        // The universal stat layer. Not optional: on one chassis, Agility and
        // Intellect do nothing for most builds without it, and a Hero who spent
        // points there would have spent them on nothing.
        {
            // A feral weapon's attack power in Cat, Bear, Dire Bear and Moonkin
            // form, on top of the chassis's own formula (which already gives
            // more base attack power than the druid one it replaces).
            int32 feralAP = 0;
            switch (player->GetShapeshiftForm())
            {
                case FORM_CAT:
                case FORM_BEAR:
                case FORM_DIREBEAR:
                case FORM_MOONKIN:
                    feralAP = CW_FeralWeaponAP(player);
                    break;
                default:
                    break;
            }
            if (feralAP != st.usFeralAP)
            {
                player->HandleStatFlatModifier(UNIT_MOD_ATTACK_POWER, TOTAL_VALUE, float(feralAP - st.usFeralAP), true);
                st.usFeralAP = feralAP;
            }

            int32 agi = int32(player->GetStat(STAT_AGILITY));
            int32 intel = int32(player->GetStat(STAT_INTELLECT));
            int32 meleeAP = int32(agi * cfg.usMeleeAPPerAgi);
            int32 rangedAP = int32(agi * cfg.usRangedAPPerAgi);
            int32 spellPower = int32(std::max<int32>(0, intel - 10) * cfg.usSpellPowerPerInt);

            if (meleeAP != st.usMeleeAP)
            {
                player->HandleStatFlatModifier(UNIT_MOD_ATTACK_POWER, TOTAL_VALUE, float(meleeAP - st.usMeleeAP), true);
                st.usMeleeAP = meleeAP;
            }
            if (rangedAP != st.usRangedAP)
            {
                player->HandleStatFlatModifier(UNIT_MOD_ATTACK_POWER_RANGED, TOTAL_VALUE, float(rangedAP - st.usRangedAP), true);
                st.usRangedAP = rangedAP;
            }
            if (spellPower != st.usSpellPower)
            {
                player->ApplySpellPowerBonus(spellPower - st.usSpellPower, true);
                st.usSpellPower = spellPower;
            }
        }

    }

    // Rebirth's XP rate. Kills and dungeons are where a reborn Hero levels,
    // since the quests they already did are the ones they forgot; everything
    // else gets the gentler curve. The Dungeon Finder's completion reward
    // arrives as a quest (XPSOURCE_QUEST_DF), so it is named here too.
    void OnPlayerGiveXP(Player* player, uint32& amount, Unit* /*victim*/, uint8 xpSource) override
    {
        if (!sClasslessMgr->cfg.enabled || !amount)
            return;
        bool const killRate = xpSource == XPSOURCE_KILL || xpSource == XPSOURCE_QUEST_DF;
        if (uint32 const pct = sClasslessMgr->RebirthXpPct(player, killRate))
            amount += CalculatePct(amount, pct);
    }

    void OnPlayerLevelChanged(Player* player, uint8 oldLevel) override
    {
        if (sClasslessMgr->cfg.enabled)
            sClasslessMgr->HandleLevelUp(player, oldLevel);
        // a level-up recalculates the points, so put them back to zero
        if (sClasslessMgr->cfg.enabled && !sClasslessMgr->IsExempt(player))
            player->SetFreeTalentPoints(0);
    }

    // Talents flow through the module — suppress the native talent frame
    // economy (except for exempt bot/system accounts, which play vanilla).
    //
    // Report the points the Hero has ALREADY SPENT, not zero. Two things
    // depend on it:
    //
    //   * InitTalentForLevel does `if (m_usedTalentCount > talentPointsForLevel)
    //     resetTalents(true)` — with zero here, the first talent the module
    //     records would wipe every talent the character owns on the next
    //     level-up or login.
    //   * The other branch is `SetFreeTalentPoints(talentPointsForLevel -
    //     m_usedTalentCount)`, and free points have to stay at zero or the
    //     stock frame runs a second talent economy beside this one.
    //
    // The exact used count would satisfy both at once, but m_usedTalentCount is
    // protected and the module cannot read it; deriving it from the module's own
    // state would be a guess that costs a character every talent it owns if the
    // two ever disagree by one — at login, mid-respec, or in any order the core
    // decides to call this. So report a ceiling no Hero can reach, which makes
    // the reset branch unreachable, and put the free points back to zero
    // wherever the module can reach them (below, and after every grant). The
    // stock frame is refused by OnPlayerCanLearnTalent regardless, so the worst
    // case is a number in a window the module replaces.
    static constexpr uint32 TALENT_POINT_CEILING = 500;

    void OnPlayerCalculateTalentsPoints(Player const* player, uint32& talentPointsForLevel) override
    {
        if (!sClasslessMgr->cfg.enabled)
            return;
        if (sClasslessMgr->IsExempt(const_cast<Player*>(player)))
            return;
        talentPointsForLevel = TALENT_POINT_CEILING;
    }


    bool OnPlayerCanLearnTalent(Player* player, TalentEntry const* /*talent*/, uint32 /*rank*/) override
    {
        if (!sClasslessMgr->cfg.enabled)
            return true;
        return sClasslessMgr->IsExempt(player);
    }

    // Class trainers (and quest rewards) would bypass the essence/roll economy:
    // a Warrior chassis could still buy warrior spells for gold. When a
    // class-library spell is learned outside the module, revert it and point
    // the player at the Hero Advancement system instead.
    void OnPlayerLearnSpell(Player* player, uint32 spellID) override
    {
        using namespace ClasslessWildcard;

        Config const& cfg = sClasslessMgr->cfg;
        if (!cfg.enabled)
            return;
        if (sClasslessMgr->IsApplyingGrant())
            return; // our own grant
        if (!player->IsInWorld())
            return; // character-creation starter spells
        if (sClasslessMgr->IsExempt(player))
            return; // bot/system accounts learn spells normally

        for (uint32 allowed : cfg.proficiencySpells)
            if (allowed == spellID)
                return;

        AbilityEntry const* e = sClasslessMgr->FindAbilityBySpell(spellID);
        if (!e)
            return; // not part of the classless library (professions, mounts, ...)

        CharState& st = sClasslessMgr->GetState(player);
        if (st.mode == Mode::Unchosen || st.abilities.count(e->firstSpellId))
            return; // no mode yet, or a rank of a line the Hero legitimately owns

        // A class trainer takes the gold in Trainer::TeachSpell and teaches the
        // spell immediately afterwards, so by the time this fires the Hero has
        // already paid for something they are about to lose. Give it back.
        // Only a debit from this same world tick counts, which is the one the
        // trainer just took: the two happen inside a single opcode.
        uint32 refund = 0;
        std::lock_guard<std::mutex> spendGuard(_lastSpendLock);
        if (auto itr = _lastSpend.find(player->GetGUID().GetCounter()); itr != _lastSpend.end())
            if (itr->second.tick == uint32(GameTime::GetGameTimeMS().count()))
            {
                refund = itr->second.copper;
                itr->second.copper = 0;   // never refund the same payment twice
            }

        // revert after the learn completes (safe outside the learn call stack)
        uint32 firstSpell = e->firstSpellId;
        player->m_Events.AddEventAtOffset([player, firstSpell, refund]()
        {
            AbilityEntry const* entry = sClasslessMgr->GetAbility(firstSpell);
            if (!entry)
                return;
            for (uint32 rankSpell : entry->ranks)
                if (player->HasSpell(rankSpell))
                    player->removeSpell(rankSpell, SPEC_MASK_ALL, false);
            if (refund)
                player->ModifyMoney(int32(refund));
            bool const wildcard = sClasslessMgr->GetState(player).mode == Mode::Wildcard;
            std::string text = Acore::StringFormat("|cff00ccff[Classless]|r Heroes cannot learn {} this way. {}",
                sClasslessMgr->SpellNameOf(firstSpell),
                wildcard ? "Wildcard abilities come from your rolls."
                         : "Buy it with Ability Essence in /cw or at the Hero Advancement NPC.");
            if (refund)
                text += " Your money has been returned.";
            ChatHandler(player->GetSession()).SendSysMessage(text);
        }, 1ms);
    }
};

// There was a spell script here that waived SPELL_FAILED_NO_POWER for any
// ability drawing on a pool other than the displayed one. It did nothing, and
// it must not be brought back:
//
//   * Spell::CheckCast calls the OnSpellCheckCast hook as its FIRST statement,
//     with the result still SPELL_CAST_OK, so no check has run yet and the
//     failure it was looking for can never be seen.
//   * Nothing is missing. Spell::CheckPower reads the pool the SPELL uses, not
//     the one on the unit frame, and RegenerateAll refills energy and mana for
//     every class while the module keeps rage flowing. A Hero with rage casts
//     rage abilities; a Hero without rage should not.
//   * Had it worked it would have been a hole: every off-chassis ability would
//     have been castable on an empty pool, which is most of a classless build.


// =====================================================================
// Stock spells that ask which bar you are showing
//
// A Hero has mana, rage and energy at once and the client can only draw one of
// them, so "what power type are you" is a question about a UI limit, not about
// the character. Most of the core asks it through HasActivePowerType, which
// this module answers; these two ask getPowerType() directly and hand back
// nothing when the answer is not the one they wanted.
//
// Both are the core's own implementation with that one question replaced. The
// module takes the spell_script_names binding over from the core script rather
// than adding a second script, because CheckProc handlers are ANDed across
// every script on an aura -- the core's `false` would veto the proc whatever a
// second script said.
// =====================================================================
namespace
{
    // Stock ids, stable since 3.3.5.
    constexpr uint32 SPELL_FRENZIED_REGENERATION_HEAL = 22845;
    constexpr uint32 SPELL_JUDGEMENT_OF_WISDOM_MANA = 20268;

    // Does this character use that resource? For a Hero the pool answers, not
    // the bar. Anyone the module leaves alone keeps the core's own test, so a
    // bot or an exempt character behaves exactly as it did.
    bool UsesPower(Unit* unit, Powers power)
    {
        if (!unit)
            return false;
        if (Player* player = unit->ToPlayer())
            if (sClasslessMgr->cfg.enabled && !sClasslessMgr->IsExempt(player))
                return player->GetMaxPower(power) > 0;
        return unit->getPowerType() == power;
    }
}

// 22842 - Frenzied Regeneration
class spell_cw_frenzied_regeneration : public AuraScript
{
    PrepareAuraScript(spell_cw_frenzied_regeneration);

    void HandlePeriodic(AuraEffect const* aurEff)
    {
        Unit* target = GetTarget();
        if (!UsesPower(target, POWER_RAGE))
            return;

        uint32 rage = target->GetPower(POWER_RAGE);
        if (!rage)
            return;

        int32 const mod = std::min(static_cast<int32>(rage), 100);
        int32 const points = GetSpellInfo()->Effects[EFFECT_1].CalcValue(target);
        int32 const regen = CalculatePct(target->GetMaxHealth(), points * mod / 100.f);
        target->CastCustomSpell(SPELL_FRENZIED_REGENERATION_HEAL, SPELLVALUE_BASE_POINT0,
                                regen, target, true, nullptr, aurEff);
        target->SetPower(POWER_RAGE, rage - mod);
    }

    void Register() override
    {
        OnEffectPeriodic += AuraEffectPeriodicFn(spell_cw_frenzied_regeneration::HandlePeriodic,
                                                 EFFECT_0, SPELL_AURA_PERIODIC_DUMMY);
    }
};

// 20186 - Judgement of Wisdom, the debuff that pays the attacker
class spell_cw_judgement_of_wisdom : public AuraScript
{
    PrepareAuraScript(spell_cw_judgement_of_wisdom);

    bool CheckProc(ProcEventInfo& eventInfo)
    {
        return UsesPower(eventInfo.GetActor(), POWER_MANA);
    }

    void HandleProc(AuraEffect const* aurEff, ProcEventInfo& eventInfo)
    {
        PreventDefaultAction();

        Unit* attacker = eventInfo.GetActor();
        if (!attacker)
            return;

        SpellInfo const* spellInfo = sSpellMgr->GetSpellInfo(SPELL_JUDGEMENT_OF_WISDOM_MANA);
        if (!spellInfo)
            return;

        int32 bp = int32(CalculatePct(attacker->GetCreateMana(),
                                      spellInfo->Effects[EFFECT_0].CalcValue()));
        attacker->CastCustomSpell(attacker, SPELL_JUDGEMENT_OF_WISDOM_MANA, &bp, nullptr, nullptr,
                                  true, nullptr, aurEff, GetCasterGUID());
    }

    void Register() override
    {
        DoCheckProc += AuraCheckProcFn(spell_cw_judgement_of_wisdom::CheckProc);
        OnEffectProc += AuraEffectProcFn(spell_cw_judgement_of_wisdom::HandleProc,
                                         EFFECT_0, SPELL_AURA_DUMMY);
    }
};

// 61013 - Warlock Pet Scaling 05, 61017 - Hunter Pet Scaling 04
//
// How much of the owner's hit and expertise a pet inherits. The core picks the
// source with `IsClass(CLASS_HUNTER, ...)` and then `getPowerType()` -- the bar
// the player happens to be SHOWING. A Hero has mana, rage and energy at once
// and chooses which one is on the main bar, so a pet's hit and expertise moved
// every time its owner clicked a mini-bar.
//
// The third spell in this file with that fault, and the same fix: ask the pool
// rather than the bar. The class test goes the same way -- what it stands in
// for is "is this a hunter's pet", which the pet itself can answer, so a Hero
// with a tamed beast inherits ranged hit the way a hunter does whatever the
// chassis is.
//
// Everything else is the core's own script, copied so the binding can be taken
// over whole: spell_script_names is a multimap and both scripts would otherwise
// calculate, with the loser's answer landing second.
class spell_cw_pet_hit_expertise_scaling : public AuraScript
{
    PrepareAuraScript(spell_cw_pet_hit_expertise_scaling);

    static int32 Percent(float hitChance, float cap, float maxChance)
    {
        return int32((hitChance / cap) * maxChance);
    }

    // `maxChance` is the effect's own ceiling: 8 for hit, 17 for spell hit,
    // 26 for expertise, exactly as the core passes them.
    int32 Inherited(float maxChance)
    {
        Unit* pet = GetUnitOwner();
        Player* modOwner = pet ? pet->GetSpellModOwner() : nullptr;
        if (!modOwner)
            return 0;

        bool hunterPet = false;
        if (Pet const* asPet = pet->ToPet())
            hunterPet = asPet->getPetType() == HUNTER_PET;

        if (hunterPet || modOwner->IsClass(CLASS_HUNTER, CLASS_CONTEXT_STATS))
            return Percent(modOwner->m_modRangedHitChance, 8.0f, maxChance);
        if (UsesPower(modOwner, POWER_MANA))
            return Percent(modOwner->m_modSpellHitChance, 17.0f, maxChance);
        return Percent(modOwner->m_modMeleeHitChance, 8.0f, maxChance);
    }

    void CalculateHitAmount(AuraEffect const* /*aurEff*/, int32& amount, bool& /*recalc*/)
    {
        amount = Inherited(8.0f);
    }

    void CalculateSpellHitAmount(AuraEffect const* /*aurEff*/, int32& amount, bool& /*recalc*/)
    {
        amount = Inherited(17.0f);
    }

    void CalculateExpertiseAmount(AuraEffect const* /*aurEff*/, int32& amount, bool& /*recalc*/)
    {
        amount = Inherited(26.0f);
    }

    void HandleEffectApply(AuraEffect const* aurEff, AuraEffectHandleModes /*mode*/)
    {
        GetUnitOwner()->ApplySpellImmune(GetId(), IMMUNITY_STATE, aurEff->GetAuraType(), true,
                                         SPELL_BLOCK_TYPE_POSITIVE);
    }

    void CalcPeriodic(AuraEffect const* /*aurEff*/, bool& isPeriodic, int32& amplitude)
    {
        if (!GetUnitOwner()->IsPet())
            return;

        isPeriodic = true;
        amplitude = 3 * IN_MILLISECONDS;
    }

    void HandlePeriodic(AuraEffect const* aurEff)
    {
        PreventDefaultAction();
        GetEffect(aurEff->GetEffIndex())->RecalculateAmount();
    }

    void Register() override
    {
        DoEffectCalcAmount += AuraEffectCalcAmountFn(
            spell_cw_pet_hit_expertise_scaling::CalculateHitAmount, EFFECT_0, SPELL_AURA_MOD_HIT_CHANCE);
        DoEffectCalcAmount += AuraEffectCalcAmountFn(
            spell_cw_pet_hit_expertise_scaling::CalculateSpellHitAmount, EFFECT_1, SPELL_AURA_MOD_SPELL_HIT_CHANCE);
        DoEffectCalcAmount += AuraEffectCalcAmountFn(
            spell_cw_pet_hit_expertise_scaling::CalculateExpertiseAmount, EFFECT_2, SPELL_AURA_MOD_EXPERTISE);

        OnEffectApply += AuraEffectApplyFn(
            spell_cw_pet_hit_expertise_scaling::HandleEffectApply, EFFECT_ALL, SPELL_AURA_ANY,
            AURA_EFFECT_HANDLE_REAL);
        DoEffectCalcPeriodic += AuraEffectCalcPeriodicFn(
            spell_cw_pet_hit_expertise_scaling::CalcPeriodic, EFFECT_ALL, SPELL_AURA_ANY);
        OnEffectPeriodic += AuraEffectPeriodicFn(
            spell_cw_pet_hit_expertise_scaling::HandlePeriodic, EFFECT_ALL, SPELL_AURA_ANY);
    }
};

// -49182 Blade Barrier, and -49208 / -49467 / -54639 Death Rune
//
// Four Death Knight talents a Hero can buy and could never make work. Their
// core scripts ask `getClass() != CLASS_DEATH_KNIGHT` outright -- a raw
// comparison with no hook behind it -- and return before touching a rune, so
// Blade Barrier never procs and Blood of the North, Reaping and Death Rune
// Mastery never convert a rune. Everything else in them already works for a
// Hero: the module allocates m_runes, ticks their cooldowns and refills runic
// power, all off CLASS_CONTEXT_ABILITY.
//
// These are the core's own implementations with that one question asked the way
// the rest of the module asks it. A real Death Knight answers yes through the
// core, a Hero answers yes through this module when Death Knight content is on,
// and anyone else answers no and keeps the core's behaviour exactly -- which
// matters, because the rune accessors dereference m_runes with no null check
// and a player without runes must never reach them.
class spell_cw_dk_blade_barrier : public AuraScript
{
    PrepareAuraScript(spell_cw_dk_blade_barrier);

    bool CheckProc(ProcEventInfo& eventInfo)
    {
        if (eventInfo.GetSpellInfo())
            if (Player* player = eventInfo.GetActor()->ToPlayer())
                if (player->IsClass(CLASS_DEATH_KNIGHT, CLASS_CONTEXT_ABILITY)
                    && player->IsBaseRuneSlotsOnCooldown(RUNE_BLOOD))
                    return true;

        return false;
    }

    void Register() override
    {
        DoCheckProc += AuraCheckProcFn(spell_cw_dk_blade_barrier::CheckProc);
    }
};

class spell_cw_dk_death_rune : public AuraScript
{
    PrepareAuraScript(spell_cw_dk_death_rune);

    bool Load() override
    {
        Player* owner = GetUnitOwner() ? GetUnitOwner()->ToPlayer() : nullptr;
        return owner && owner->IsClass(CLASS_DEATH_KNIGHT, CLASS_CONTEXT_ABILITY);
    }

    bool CheckProc(ProcEventInfo& eventInfo)
    {
        Unit* caster = eventInfo.GetActor();
        if (!caster || !caster->IsPlayer())
            return false;

        return caster->ToPlayer()->IsClass(CLASS_DEATH_KNIGHT, CLASS_CONTEXT_ABILITY);
    }

    void HandleProc(ProcEventInfo& eventInfo)
    {
        Player* player = eventInfo.GetActor()->ToPlayer();
        AuraEffect* aurEff = GetEffect(EFFECT_0);
        if (!aurEff)
            return;

        // Reset amplitude - set death rune remove timer to 30s
        aurEff->ResetPeriodic(true);

        uint32 runesLeft = 1;
        // Death Rune Mastery (SpellIconID 2622)
        if (GetSpellInfo()->SpellIconID == 2622)
            runesLeft = 2;

        for (uint8 i = 0; i < MAX_RUNES && runesLeft; ++i)
        {
            if (GetSpellInfo()->SpellIconID == 2622)
            {
                if (player->GetBaseRune(i) == RUNE_BLOOD)
                    continue;
            }
            else
            {
                if (player->GetBaseRune(i) != RUNE_BLOOD)
                    continue;
            }

            // Check if rune just went on cooldown
            if (player->GetRuneCooldown(i) != player->GetRuneBaseCooldown(i, false))
                continue;

            --runesLeft;
            player->AddRuneByAuraEffect(i, RUNE_DEATH, aurEff);
        }
    }

    void PeriodicTick(AuraEffect const* aurEff)
    {
        if (Player* player = GetTarget() ? GetTarget()->ToPlayer() : nullptr)
            player->RemoveRunesByAuraEffect(aurEff);
    }

    void Register() override
    {
        DoCheckProc += AuraCheckProcFn(spell_cw_dk_death_rune::CheckProc);
        OnProc += AuraProcFn(spell_cw_dk_death_rune::HandleProc);
        OnEffectPeriodic += AuraEffectPeriodicFn(spell_cw_dk_death_rune::PeriodicTick,
                                                 EFFECT_0, SPELL_AURA_PERIODIC_DUMMY);
    }
};

// 2457 Battle Stance, 71 Defensive Stance, 2458 Berserker Stance.
//
// A stance's shapeshift handler sets the bar to rage when it is not already
// (HandleAuraModShapeshift), and Unit::setPowerType empties the rage pool when
// it does. A Warrior's bar is always rage, so that never happens to one; a
// Hero's bar is mana again between stances (Player::InitDataForForm), so every
// stance a Hero entered emptied their rage, and Tactical Mastery and Stance
// Mastery kept nothing. The rage is held across that reset and given back.
//
// On a stance change the order is: the new stance's OnEffectApply (held), the
// old stance coming off inside its handler (its AfterEffectRemove holds the
// rage the core has just capped to what the talents keep), the reset, and the
// new stance's AfterEffectApply (given back). From no stance, all of it.
class spell_cw_warrior_stance : public AuraScript
{
    PrepareAuraScript(spell_cw_warrior_stance);

    static CharState* HeroState(Unit* unit)
    {
        Player* player = unit ? unit->ToPlayer() : nullptr;
        if (!player || sClasslessMgr->IsExempt(player))
            return nullptr;
        return sClasslessMgr->FindState(player);
    }

    void Hold(AuraEffect const* /*aurEff*/, AuraEffectHandleModes /*mode*/)
    {
        if (CharState* st = HeroState(GetTarget()))
            st->stanceRage = GetTarget()->GetPower(POWER_RAGE);
    }

    void GiveBack(AuraEffect const* /*aurEff*/, AuraEffectHandleModes /*mode*/)
    {
        CharState* st = HeroState(GetTarget());
        if (!st)
            return;
        Unit* target = GetTarget();
        uint32 const kept = std::min<uint32>(st->stanceRage, target->GetMaxPower(POWER_RAGE));
        if (target->GetPower(POWER_RAGE) < kept)
            target->SetPower(POWER_RAGE, kept);
    }

    void Register() override
    {
        OnEffectApply += AuraEffectApplyFn(spell_cw_warrior_stance::Hold,
            EFFECT_0, SPELL_AURA_MOD_SHAPESHIFT, AURA_EFFECT_HANDLE_REAL);
        AfterEffectRemove += AuraEffectRemoveFn(spell_cw_warrior_stance::Hold,
            EFFECT_0, SPELL_AURA_MOD_SHAPESHIFT, AURA_EFFECT_HANDLE_REAL);
        AfterEffectApply += AuraEffectApplyFn(spell_cw_warrior_stance::GiveBack,
            EFFECT_0, SPELL_AURA_MOD_SHAPESHIFT, AURA_EFFECT_HANDLE_REAL);
    }
};

// 70656 Advantage, the Death Knight tier-10 melee 4-piece. The core's script
// gives it to a Death Knight by getClass() only, so a Hero in the set never got
// it. It asks for runes instead, the way the module answers a Death Knight's
// abilities (CharState::runes): the rune block it reads exists only then.
class spell_cw_dk_advantage_t10_4p : public AuraScript
{
    PrepareAuraScript(spell_cw_dk_advantage_t10_4p);

    bool CheckProc(ProcEventInfo& eventInfo)
    {
        Player* player = eventInfo.GetActor() ? eventInfo.GetActor()->ToPlayer() : nullptr;
        if (!player || !player->IsClass(CLASS_DEATH_KNIGHT, CLASS_CONTEXT_ABILITY))
            return false;
        for (uint8 i = 0; i < MAX_RUNES; ++i)
            if (player->GetRuneCooldown(i) == 0)
                return false;
        return true;
    }

    void Register() override
    {
        DoCheckProc += AuraCheckProcFn(spell_cw_dk_advantage_t10_4p::CheckProc);
    }
};

// Item and set procs that pick their reward by CLASS. The core switches on
// getClass() directly, so a Hero always took the chassis's answer: Eye of
// Gruul and Soul Preserver cheapened Paladin heals only, whatever the Hero
// healed with; Flask of the North never offered attack power. A Hero is every
// class at once, so each of these treats one that way: every per-class reward
// where the rewards cover different spells, and a random one where they are
// alternatives, the way the core already rolls for its hybrid classes. Anyone
// else gets the core's own behaviour, line for line.
namespace
{
    bool IsHeroUnit(Unit const* unit)
    {
        Player* player = unit ? const_cast<Unit*>(unit)->ToPlayer() : nullptr;
        return player && sClasslessMgr->cfg.enabled && !sClasslessMgr->IsExempt(player);
    }

    // druid, paladin, priest, shaman: the classes the per-class healing items
    // name, in that order; -1 for any other
    int32 HealerIndex(Unit const* unit)
    {
        switch (unit->getClass())
        {
            case CLASS_DRUID:   return 0;
            case CLASS_PALADIN: return 1;
            case CLASS_PRIEST:  return 2;
            case CLASS_SHAMAN:  return 3;
            default:            return -1;
        }
    }

    // T3 6-piece Holy Power and Totemic Power, by the target's class:
    // mp5, spell power, attack power, armor
    int32 T3BuffIndex(Unit const* unit)
    {
        switch (unit->getClass())
        {
            case CLASS_PALADIN: case CLASS_PRIEST: case CLASS_SHAMAN: case CLASS_DRUID: return 0;
            case CLASS_MAGE: case CLASS_WARLOCK: return 1;
            case CLASS_HUNTER: case CLASS_ROGUE: return 2;
            case CLASS_WARRIOR: return 3;
            default: return -1;
        }
    }
}

// 37705 Healing Discount (Eye of Gruul), 60510 Soul Preserver
class spell_cw_healing_trance : public AuraScript
{
    PrepareAuraScript(spell_cw_healing_trance);

    static constexpr uint32 EYE_OF_GRUUL[4]   = { 37721, 37723, 37706, 37722 };
    static constexpr uint32 SOUL_PRESERVER[4] = { 60512, 60513, 60514, 60515 };

    bool Validate(SpellInfo const* /*spellInfo*/) override
    {
        return ValidateSpellInfo({ 37721, 37723, 37706, 37722, 60512, 60513, 60514, 60515 });
    }

    void HandleProc(AuraEffect const* aurEff, ProcEventInfo& /*eventInfo*/)
    {
        PreventDefaultAction();
        Unit* target = GetTarget();
        if (!target)
            return;
        uint32 const* trances = GetSpellInfo()->Id == 37705 ? EYE_OF_GRUUL : SOUL_PRESERVER;
        if (IsHeroUnit(target))
        {
            for (uint8 i = 0; i < 4; ++i)
                target->CastSpell(target, trances[i], true, nullptr, aurEff);
            return;
        }
        if (int32 const index = HealerIndex(target); index >= 0)
            target->CastSpell(target, trances[index], true, nullptr, aurEff);
    }

    void Register() override
    {
        OnEffectProc += AuraEffectProcFn(spell_cw_healing_trance::HandleProc, EFFECT_0, SPELL_AURA_PROC_TRIGGER_SPELL);
    }
};

// 37877 Blessing of Faith
class spell_cw_blessing_of_faith : public SpellScript
{
    PrepareSpellScript(spell_cw_blessing_of_faith);

    static constexpr uint32 LOWER_CITY[4] = { 37878, 37879, 37880, 37881 };

    bool Validate(SpellInfo const* /*spellInfo*/) override
    {
        return ValidateSpellInfo({ 37878, 37879, 37880, 37881 });
    }

    void HandleDummy(SpellEffIndex /*effIndex*/)
    {
        Unit* target = GetHitUnit();
        Unit* caster = GetCaster();
        if (!target || !caster)
            return;
        if (IsHeroUnit(target))
        {
            for (uint32 spellId : LOWER_CITY)
                caster->CastSpell(caster, spellId, true);
            return;
        }
        if (int32 const index = HealerIndex(target); index >= 0)
            caster->CastSpell(caster, LOWER_CITY[index], true);
    }

    void Register() override
    {
        OnEffectHitTarget += SpellEffectFn(spell_cw_blessing_of_faith::HandleDummy, EFFECT_0, SPELL_EFFECT_DUMMY);
    }
};

// 67019 Flask of the North
class spell_cw_flask_of_the_north : public SpellScript
{
    PrepareSpellScript(spell_cw_flask_of_the_north);

    static constexpr uint32 SPELL_POWER = 67016, ATTACK_POWER = 67017, STRENGTH = 67018;

    bool Validate(SpellInfo const* /*spellInfo*/) override
    {
        return ValidateSpellInfo({ SPELL_POWER, ATTACK_POWER, STRENGTH });
    }

    void HandleDummy(SpellEffIndex /*effIndex*/)
    {
        Unit* caster = GetCaster();
        if (!caster)
            return;
        std::vector<uint32> possible;
        if (IsHeroUnit(caster))
            possible = { SPELL_POWER, ATTACK_POWER, STRENGTH };
        else
            switch (caster->getClass())
            {
                case CLASS_WARLOCK: case CLASS_MAGE: case CLASS_PRIEST:
                    possible = { SPELL_POWER };
                    break;
                case CLASS_DEATH_KNIGHT: case CLASS_WARRIOR:
                    possible = { STRENGTH };
                    break;
                case CLASS_ROGUE: case CLASS_HUNTER:
                    possible = { ATTACK_POWER };
                    break;
                case CLASS_DRUID: case CLASS_PALADIN:
                    possible = { SPELL_POWER, STRENGTH };
                    break;
                case CLASS_SHAMAN:
                    possible = { SPELL_POWER, ATTACK_POWER };
                    break;
                default:
                    break;
            }
        if (!possible.empty())
            caster->CastSpell(caster, Acore::Containers::SelectRandomContainerElement(possible), true);
    }

    void Register() override
    {
        OnEffectHit += SpellEffectFn(spell_cw_flask_of_the_north::HandleDummy, EFFECT_0, SPELL_EFFECT_DUMMY);
    }
};

// 28789 Holy Power and 28823 Totemic Power, the T3 6-piece bonuses
class spell_cw_t3_6p_bonus : public AuraScript
{
    PrepareAuraScript(spell_cw_t3_6p_bonus);

    // mp5, spell power, attack power, armor
    static constexpr uint32 HOLY_POWER[4]    = { 28795, 28793, 28791, 28790 };
    static constexpr uint32 TOTEMIC_POWER[4] = { 28824, 28825, 28826, 28827 };

    bool Validate(SpellInfo const* /*spellInfo*/) override
    {
        return ValidateSpellInfo({ 28795, 28793, 28791, 28790, 28824, 28825, 28826, 28827 });
    }

    void HandleProc(AuraEffect const* aurEff, ProcEventInfo& eventInfo)
    {
        PreventDefaultAction();
        Unit* caster = eventInfo.GetActor();
        Unit* target = eventInfo.GetActionTarget();
        if (!caster || !target)
            return;
        uint32 const* buffs = GetSpellInfo()->Id == 28789 ? HOLY_POWER : TOTEMIC_POWER;
        int32 const index = IsHeroUnit(target) ? int32(urand(0, 3)) : T3BuffIndex(target);
        if (index >= 0)
            caster->CastSpell(target, buffs[index], true, nullptr, aurEff);
    }

    void Register() override
    {
        OnEffectProc += AuraEffectProcFn(spell_cw_t3_6p_bonus::HandleProc, EFFECT_0, SPELL_AURA_DUMMY);
    }
};

// Which list a Hero's trinket rolls from: the one for the stat the Hero has the
// most of, Strength, Agility or Intellect.
enum class CW_BestStat { Strength, Agility, Intellect };

static CW_BestStat CW_HeroBestStat(Unit const* unit)
{
    float const str = unit->GetStat(STAT_STRENGTH);
    float const agi = unit->GetStat(STAT_AGILITY);
    float const intel = unit->GetStat(STAT_INTELLECT);
    if (intel > str && intel > agi)
        return CW_BestStat::Intellect;
    return agi > str ? CW_BestStat::Agility : CW_BestStat::Strength;
}

// 71519 Deathbringer's Will, 71562 heroic. The core rolls from a per-class list,
// so a Hero always rolled the Paladin's (Strength, crit, haste), even an Agility
// build. A Hero rolls from the Strength list (the Warrior's) or the Agility list
// (the Rogue's), whichever stat is higher; the trinket has no caster list.
class spell_cw_deathbringers_will : public AuraScript
{
    PrepareAuraScript(spell_cw_deathbringers_will);

    // strength, agility, attack power, crit, haste
    static constexpr uint32 NORMAL[5] = { 71484, 71485, 71486, 71491, 71492 };
    static constexpr uint32 HEROIC[5] = { 71561, 71556, 71558, 71559, 71560 };
    enum { STR, AGI, AP, CRIT, HASTE };

    bool Validate(SpellInfo const* /*spellInfo*/) override
    {
        return ValidateSpellInfo({ 71484, 71485, 71486, 71491, 71492, 71561, 71556, 71558, 71559, 71560 });
    }

    void HandleProc(AuraEffect const* aurEff, ProcEventInfo& eventInfo)
    {
        PreventDefaultAction();
        Unit* caster = eventInfo.GetActor();
        if (!caster)
            return;
        uint32 const* s = GetSpellInfo()->Id == 71562 ? HEROIC : NORMAL;
        std::vector<uint32> possible;
        if (IsHeroUnit(caster))
            possible = CW_HeroBestStat(caster) == CW_BestStat::Agility
                ? std::vector<uint32>{ s[AGI], s[HASTE], s[AP] }
                : std::vector<uint32>{ s[STR], s[CRIT], s[HASTE] };
        else
            switch (caster->getClass())
            {
                case CLASS_WARRIOR: case CLASS_PALADIN: case CLASS_DEATH_KNIGHT:
                    possible = { s[STR], s[CRIT], s[HASTE] };
                    break;
                case CLASS_HUNTER:
                    possible = { s[AGI], s[CRIT], s[AP] };
                    break;
                case CLASS_ROGUE: case CLASS_SHAMAN:
                    possible = { s[AGI], s[HASTE], s[AP] };
                    break;
                case CLASS_DRUID:
                    possible = { s[STR], s[AGI], s[HASTE] };
                    break;
                default:
                    break;
            }
        if (!possible.empty())
            caster->CastSpell(caster, Acore::Containers::SelectRandomContainerElement(possible), true, nullptr, aurEff);
    }

    void Register() override
    {
        OnEffectProc += AuraEffectProcFn(spell_cw_deathbringers_will::HandleProc, EFFECT_0, SPELL_AURA_DUMMY);
    }
};

// 39446 Aura of Madness, Darkmoon Card: Madness. The core gives the Paladin all
// nine madnesses, melee and caster alike. A Hero rolls the caster list when
// Intellect is the highest stat, otherwise the melee list.
class spell_cw_aura_of_madness : public AuraScript
{
    PrepareAuraScript(spell_cw_aura_of_madness);

    enum
    {
        SOCIOPATH = 39511, DELUSIONAL = 40997, KLEPTOMANIA = 40998, MEGALOMANIA = 40999,
        PARANOIA = 41002, MANIC = 41005, NARCISSISM = 41009, MARTYR_COMPLEX = 41011,
        DEMENTIA = 41404, SAY_MADNESS = 21954
    };

    bool Validate(SpellInfo const* /*spellInfo*/) override
    {
        return ValidateSpellInfo({ SOCIOPATH, DELUSIONAL, KLEPTOMANIA, MEGALOMANIA,
                                   PARANOIA, MANIC, NARCISSISM, MARTYR_COMPLEX, DEMENTIA })
            && sObjectMgr->GetBroadcastText(SAY_MADNESS);
    }

    void HandleProc(AuraEffect const* aurEff, ProcEventInfo& eventInfo)
    {
        static std::vector<uint32> const MELEE  = { SOCIOPATH, DELUSIONAL, KLEPTOMANIA, PARANOIA, MANIC, MARTYR_COMPLEX };
        static std::vector<uint32> const CASTER = { MEGALOMANIA, PARANOIA, MANIC, NARCISSISM, MARTYR_COMPLEX, DEMENTIA };
        static std::vector<uint32> const HUNTER = { DELUSIONAL, MEGALOMANIA, PARANOIA, MANIC, NARCISSISM, MARTYR_COMPLEX, DEMENTIA };
        static std::vector<uint32> const ALL    = { SOCIOPATH, DELUSIONAL, KLEPTOMANIA, MEGALOMANIA, PARANOIA, MANIC, NARCISSISM, MARTYR_COMPLEX, DEMENTIA };

        PreventDefaultAction();
        Unit* caster = eventInfo.GetActor();
        if (!caster)
            return;
        std::vector<uint32> const* possible = nullptr;
        if (IsHeroUnit(caster))
            possible = CW_HeroBestStat(caster) == CW_BestStat::Intellect ? &CASTER : &MELEE;
        else
            switch (caster->getClass())
            {
                case CLASS_WARRIOR: case CLASS_ROGUE: case CLASS_DEATH_KNIGHT:
                    possible = &MELEE;
                    break;
                case CLASS_PRIEST: case CLASS_SHAMAN: case CLASS_MAGE: case CLASS_WARLOCK:
                    possible = &CASTER;
                    break;
                case CLASS_HUNTER:
                    possible = &HUNTER;
                    break;
                case CLASS_PALADIN: case CLASS_DRUID:
                    possible = &ALL;
                    break;
                default:
                    break;
            }
        if (!possible)
            return;

        caster->CastSpell(caster, Acore::Containers::SelectRandomContainerElement(*possible), true, nullptr, aurEff);
        if (roll_chance_i(10))
            caster->Unit::Say(SAY_MADNESS);
    }

    void Register() override
    {
        OnEffectProc += AuraEffectProcFn(spell_cw_aura_of_madness::HandleProc, EFFECT_0, SPELL_AURA_DUMMY);
    }
};

// The Stable Master's "stable my pets" option. PrepareGossipMenu shows it only
// when IsClass(CLASS_HUNTER, CLASS_CONTEXT_PET) says yes, and for a Hero that
// answer follows the pet that is out (a beast is a hunter pet, a demon is not).
// So a Hero with a demon or a ghoul out lost the option, and with it the
// stabled beasts. A Hero always gets it: the menu is built the core's way, and
// the option is put back in its own place.
class ClasslessStableMasterScript : public AllCreatureScript
{
public:
    ClasslessStableMasterScript() : AllCreatureScript("ClasslessStableMasterScript") { }

    bool CanCreatureGossipHello(Player* player, Creature* creature) override
    {
        if (!player || !creature || !creature->HasNpcFlag(UNIT_NPC_FLAG_STABLEMASTER))
            return false;
        // a creature with its own gossip script builds its own menu
        if (creature->GetScriptId())
            return false;
        if (!IsHeroUnit(player) || player->IsClass(CLASS_HUNTER, CLASS_CONTEXT_PET))
            return false;

        uint32 const menuId = creature->GetGossipMenuId();
        player->PrepareGossipMenu(creature, menuId, true);

        GossipMenuItemsMapBounds bounds = sObjectMgr->GetGossipMenuItemsMapBounds(menuId);
        if (bounds.first == bounds.second && menuId == Player::GetDefaultGossipMenuForSource(creature))
            bounds = sObjectMgr->GetGossipMenuItemsMapBounds(0);

        GossipMenu& menu = player->PlayerTalkClass->GetGossipMenu();
        for (auto itr = bounds.first; itr != bounds.second; ++itr)
        {
            GossipMenuItems const& item = itr->second;
            if (item.OptionType != GOSSIP_OPTION_STABLEPET || !(item.OptionNpcFlag & creature->GetNpcFlags()))
                continue;
            if (!sConditionMgr->IsObjectMeetToConditions(player, creature, item.Conditions))
                continue;
            if (menu.GetItem(item.OptionID))
                continue;

            // the option's text the way PrepareGossipMenu finds it
            std::string optionText = item.OptionText;
            std::string boxText = item.BoxText;
            LocaleConstant const locale = player->GetSession()->GetSessionDbLocaleIndex();
            BroadcastText const* optionBroadcast = sObjectMgr->GetBroadcastText(item.OptionBroadcastTextID);
            BroadcastText const* boxBroadcast = sObjectMgr->GetBroadcastText(item.BoxBroadcastTextID);
            if (optionBroadcast)
                ObjectMgr::GetLocaleString(player->getGender() == GENDER_MALE ? optionBroadcast->MaleText : optionBroadcast->FemaleText, locale, optionText);
            if (boxBroadcast)
                ObjectMgr::GetLocaleString(player->getGender() == GENDER_MALE ? boxBroadcast->MaleText : boxBroadcast->FemaleText, locale, boxText);
            if (locale != DEFAULT_LOCALE)
                if (GossipMenuItemsLocale const* loc = sObjectMgr->GetGossipMenuItemsLocale(MAKE_PAIR32(menuId, item.OptionID)))
                {
                    if (!optionBroadcast)
                        ObjectMgr::GetLocaleString(loc->OptionText, locale, optionText);
                    if (!boxBroadcast)
                        ObjectMgr::GetLocaleString(loc->BoxText, locale, boxText);
                }

            menu.AddMenuItem(item.OptionID, item.OptionIcon, optionText, 0, item.OptionType, boxText, item.BoxMoney, item.BoxCoded);
            menu.AddGossipMenuItemData(item.OptionID, item.ActionMenuID, item.ActionPoiID);
        }

        player->SendPreparedGossip(creature);
        return true;
    }
};

// Which shapeshift form a Hero holds, for the druid answer in OnPlayerIsClass.
// Both hooks run with the form already settled: apply after the new form's
// handler has set it, remove after the old one's has cleared it. So in between
// -- while the core is handling the form coming off -- heldForm still names it.
class ClasslessFormScript : public UnitScript
{
public:
    ClasslessFormScript() : UnitScript("ClasslessFormScript", true, { UNITHOOK_ON_AURA_APPLY, UNITHOOK_ON_AURA_REMOVE }) { }

    void OnAuraApply(Unit* unit, Aura* aura) override
    {
        if (aura && aura->GetSpellInfo()->HasAura(SPELL_AURA_MOD_SHAPESHIFT))
            Track(unit);
    }

    void OnAuraRemove(Unit* unit, AuraApplication* aurApp, AuraRemoveMode /*mode*/) override
    {
        if (!aurApp || !aurApp->GetBase()->GetSpellInfo()->HasAura(SPELL_AURA_MOD_SHAPESHIFT))
            return;
        RestoreUnderlyingForm(unit, aurApp->GetBase());
        Track(unit);
    }

private:
    // A rogue shapeshift (Stealth, Shadow Dance) does not take a stance or a
    // form off (HandleAuraModShapeshift skips that for SPELLFAMILY_ROGUE), and
    // a stance, Shadowform or Moonkin Form does not stop Stealth from being
    // cast. When the rogue one ends, the core resets the form only if no other
    // shapeshift is left, so a Hero who stealthed in Battle Stance came out
    // still marked "in Stealth": stance abilities failed until another stance
    // was clicked. The form underneath is put back.
    static void RestoreUnderlyingForm(Unit* unit, Aura const* removed)
    {
        Player* player = unit ? unit->ToPlayer() : nullptr;
        SpellInfo const* info = removed->GetSpellInfo();
        if (!player || info->SpellFamilyName != SPELLFAMILY_ROGUE)
            return;
        int32 removedForm = -1;
        for (SpellEffectInfo const& effect : info->GetEffects())
            if (effect.ApplyAuraName == SPELL_AURA_MOD_SHAPESHIFT)
                removedForm = effect.MiscValue;
        if (removedForm < 0 || int32(player->GetShapeshiftForm()) != removedForm)
            return;
        for (AuraEffect const* left : player->GetAuraEffectsByType(SPELL_AURA_MOD_SHAPESHIFT))
        {
            if (left->GetBase() == removed)
                continue;
            player->SetShapeshiftForm(ShapeshiftForm(left->GetMiscValue()));
            player->InitDataForForm();
            return;
        }
    }

    static void Track(Unit* unit)
    {
        Player* player = unit ? unit->ToPlayer() : nullptr;
        if (!player)
            return;
        if (CharState* st = sClasslessMgr->FindState(player))
            st->heldForm = uint8(player->GetShapeshiftForm());
    }
};

// Holds back the core's spell modifier packets for a Hero. Their totals mix
// every class's talents onto bits the client only applies to its own class's
// spells; ClasslessMgr::SyncClientSpellMods sends the ones it can use instead.
// A character still loading passes through: the login sync overwrites it all.
class ClasslessServerScript : public ServerScript
{
public:
    ClasslessServerScript() : ServerScript("ClasslessServerScript", { SERVERHOOK_CAN_PACKET_SEND,
                                                                      SERVERHOOK_CAN_PACKET_RECEIVE }) { }

    // Trophies and the Nemesis Charm stay in the bags (PLAN-nemesis.md: locked
    // in the bags). Trading, mail, the auction house and a guild bank refuse a
    // soulbound item already; the bank does not, and the core has no hook for
    // it, so the client's move requests are read here and any that would put
    // one in the bank or a bank bag is refused. The charm cannot be destroyed.
    bool CanPacketReceive(WorldSession* session, WorldPacket const& packet) override
    {
        Player* player = session ? session->GetPlayer() : nullptr;
        if (!player || !player->IsInWorld())
            return true;
        auto lockedItem = [](Item const* item)
        {
            return item && (ClasslessMgr::IsNemesisTrophy(item->GetEntry()) || item->GetEntry() == ClasslessMgr::NEMESIS_CHARM);
        };
        // a bag counts as one when it holds one: a bag can move into a bank
        // bag slot with everything in it
        auto locked = [player, lockedItem](uint8 bag, uint8 slot)
        {
            Item* item = player->GetItemByPos(bag, slot);
            if (lockedItem(item))
                return true;
            if (Bag* container = item ? item->ToBag() : nullptr)
                for (uint32 i = 0; i < container->GetBagSize(); ++i)
                    if (lockedItem(container->GetItemByPos(uint8(i))))
                        return true;
            return false;
        };
        auto refuse = [player](char const* text)
        {
            ChatHandler(player->GetSession()).SendNotification(text);
            return false;
        };
        try
        {
            switch (packet.GetOpcode())
            {
                case CMSG_SWAP_ITEM:   // dstbag, dstslot, srcbag, srcslot
                {
                    uint8 const dstBag = packet.read<uint8>(0), dstSlot = packet.read<uint8>(1);
                    uint8 const srcBag = packet.read<uint8>(2), srcSlot = packet.read<uint8>(3);
                    if ((locked(srcBag, srcSlot) && Player::IsBankPos(dstBag, dstSlot))
                        || (locked(dstBag, dstSlot) && Player::IsBankPos(srcBag, srcSlot)))
                        return refuse("Trophies and your Nemesis Charm stay in your bags.");
                    break;
                }
                case CMSG_SWAP_INV_ITEM:   // srcslot, dstslot, both in the backpack's own range
                {
                    uint8 const srcSlot = packet.read<uint8>(0), dstSlot = packet.read<uint8>(1);
                    if ((locked(INVENTORY_SLOT_BAG_0, srcSlot) && Player::IsBankPos(INVENTORY_SLOT_BAG_0, dstSlot))
                        || (locked(INVENTORY_SLOT_BAG_0, dstSlot) && Player::IsBankPos(INVENTORY_SLOT_BAG_0, srcSlot)))
                        return refuse("Trophies and your Nemesis Charm stay in your bags.");
                    break;
                }
                case CMSG_AUTOSTORE_BAG_ITEM:   // srcbag, srcslot, dstbag
                    if (locked(packet.read<uint8>(0), packet.read<uint8>(1))
                        && Player::IsBankPos(packet.read<uint8>(2), NULL_SLOT))
                        return refuse("Trophies and your Nemesis Charm stay in your bags.");
                    break;
                case CMSG_AUTOBANK_ITEM:   // srcbag, srcslot
                    if (locked(packet.read<uint8>(0), packet.read<uint8>(1)))
                        return refuse("Trophies and your Nemesis Charm stay in your bags.");
                    break;
                case CMSG_SPLIT_ITEM:   // srcbag, srcslot, dstbag, dstslot, count
                    if (locked(packet.read<uint8>(0), packet.read<uint8>(1))
                        && Player::IsBankPos(packet.read<uint8>(2), packet.read<uint8>(3)))
                        return refuse("Trophies and your Nemesis Charm stay in your bags.");
                    break;
                case CMSG_DESTROYITEM:   // bag, slot, count, ...
                {
                    Item* item = player->GetItemByPos(packet.read<uint8>(0), packet.read<uint8>(1));
                    if (item && item->GetEntry() == ClasslessMgr::NEMESIS_CHARM)
                        return refuse("Your Nemesis Charm cannot be destroyed.");
                    break;
                }
                default:
                    break;
            }
        }
        catch (ByteBufferException const&)
        {
        }
        return true;
    }

    bool CanPacketSend(WorldSession* session, WorldPacket const& packet) override
    {
        uint16 const opcode = packet.GetOpcode();
        if (opcode != SMSG_SET_FLAT_SPELL_MODIFIER && opcode != SMSG_SET_PCT_SPELL_MODIFIER)
            return true;
        if (ClasslessMgr::IsSendingClientSpellMods() || !sClasslessMgr->cfg.enabled || !session)
            return true;
        Player* player = session->GetPlayer();
        if (!player || !player->IsInWorld())
            return true;
        CharState* st = sClasslessMgr->FindState(player);
        if (!st || st->exempt)
            return true;
        sClasslessMgr->QueueClientSpellModSync(player);
        return false;
    }
};

// General talents reach every class's abilities (ClasslessMgr::LoadTalentReach).
//
// SpellInfo::IsAffectedBySpellMod asks this before it matches a modifier's
// family and class bits, and an answer of false there means "affected". So a
// talent modifier the generator judged general applies, as itself, to the
// abilities of other classes of its kind; everything else falls through to the
// core's own family-and-bit match, unchanged. Any script answering false wins,
// so this only ever widens what a modifier reaches.
class ClasslessTalentReachScript : public GlobalScript
{
public:
    ClasslessTalentReachScript() : GlobalScript("ClasslessTalentReachScript", {
        GLOBALHOOK_ON_IS_AFFECTED_BY_SPELL_MOD_CHECK
    }) { }

    bool OnIsAffectedBySpellModCheck(SpellInfo const* affectSpell, SpellInfo const* checkSpell,
                                     SpellModifier const* mod) override
    {
        if (!affectSpell || !checkSpell || !mod)
            return true;
        return !sClasslessMgr->TalentReaches(affectSpell->Id, uint8(mod->op), checkSpell->Id);
    }
};

void AddClasslessPlayerScripts()
{
    new ClasslessTalentReachScript();
    new ClasslessWorldScript();
    new ClasslessServerScript();
    new ClasslessFormScript();
    new ClasslessPlayerScript();
    new ClasslessStableMasterScript();
    RegisterSpellScript(spell_cw_frenzied_regeneration);
    RegisterSpellScript(spell_cw_judgement_of_wisdom);
    RegisterSpellScript(spell_cw_pet_hit_expertise_scaling);
    RegisterSpellScript(spell_cw_dk_blade_barrier);
    RegisterSpellScript(spell_cw_dk_death_rune);
    RegisterSpellScript(spell_cw_healing_trance);
    RegisterSpellScript(spell_cw_blessing_of_faith);
    RegisterSpellScript(spell_cw_flask_of_the_north);
    RegisterSpellScript(spell_cw_t3_6p_bonus);
    RegisterSpellScript(spell_cw_deathbringers_will);
    RegisterSpellScript(spell_cw_aura_of_madness);
    RegisterSpellScript(spell_cw_warrior_stance);
    RegisterSpellScript(spell_cw_dk_advantage_t10_4p);
}
