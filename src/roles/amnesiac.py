import re
import random
import itertools
import math
from collections import defaultdict

from src.utilities import *
from src import channels, users, debuglog, errlog, plog
from src.functions import get_players, get_all_players, get_main_role, get_reveal_role, get_target, is_known_wolf_ally
from src.decorators import command, event_listener
from src.containers import UserList, UserSet, UserDict, DefaultUserDict
from src.messages import messages
from src.events import Event

ROLES = UserDict()  # type: Dict[users.User, str]
STATS_FLAG = False # if True, we begin accounting for amnesiac in update_stats

def _get_blacklist(var):
    # matchmaker is blacklisted if AMNESIAC_NIGHTS > 1 due to only being able to act night 1.

    # clone and traitor are blacklisted due to assumptions made in default !stats computations.
    # If you remove these from the blacklist you will need to modify the default !stats logic
    # chains in order to correctly account for these. As a forewarning, such modifications are
    # nontrivial and will likely require a great deal of thought (and likely new tracking vars)
    # FIXME: once experimental stats become the new stats, clone and traitor will work properly
    # and we can remove those from hardcoded blacklist and remove this comment block.
    blacklist = var.TEMPLATE_RESTRICTIONS.keys() | var.AMNESIAC_BLACKLIST | {var.DEFAULT_ROLE, "amnesiac", "clone", "traitor"}
    if var.AMNESIAC_NIGHTS > 1:
        blacklist.add("matchmaker")
    return blacklist

@event_listener("transition_night_begin")
def on_transition_night_begin(evt, var):
    global STATS_FLAG
    if var.NIGHT_COUNT == var.AMNESIAC_NIGHTS:
        amnesiacs = get_all_players(("amnesiac",))
        if amnesiacs and not var.HIDDEN_AMNESIAC:
            STATS_FLAG = True

        for amn in amnesiacs:
            role = ROLES[amn]
            evt = Event("new_role", {"messages": [], "role": role}, old_player=None)
            evt.dispatch(var, amn, "amnesiac")
            change_role(amn, "amnesiac", evt.data["role"])
            if var.FIRST_NIGHT: # we don't need to tell them twice if they remember right away
                continue
            showrole = evt.data["role"]
            if showrole in var.HIDDEN_VILLAGERS:
                showrole = "villager"
            elif showrole in var.HIDDEN_ROLES:
                showrole = var.DEFAULT_ROLE
            a = "a"
            if showrole.startswith(("a", "e", "i", "o", "u")):
                a = "an"
            amn.send(messages["amnesia_clear"].format(a, showrole))
            amn.send(*evt.data["messages"])
            if is_known_wolf_ally(amn, amn):
                if evt.data["role"] in var.WOLF_ROLES:
                    relay_wolfchat_command(amn.client, amn.nick, messages["amnesia_wolfchat"].format(amn, showrole), var.WOLF_ROLES, is_wolf_command=True, is_kill_command=True)
                else:
                    relay_wolfchat_command(amn.client, amn.nick, messages["amnesia_wolfchat"].format(amn, showrole), var.WOLFCHAT_ROLES)

            debuglog("{0} REMEMBER: {1} as {2}".format(amn, evt.data["role"], showrole))

@event_listener("new_role")
def doctor_new_role(evt, var, user, old_role):
    if evt.data["role"] == "doctor": # FIXME: Need to split into doctor.py when split
        var.DOCTORS[user.nick] = math.ceil(var.DOCTOR_IMMUNIZATION_MULTIPLIER * len(get_players()))

@event_listener("investigate")
def on_investigate(evt, var, actor, target):
    if evt.data["role"] == "amnesiac":
        evt.data["role"] = ROLES[target]

@event_listener("new_role", priority=1) # Exchange, clone, etc. - assign the amnesiac's final role
def update_amnesiac(evt, var, user, old_role):
    # FIXME: exchange totem messes with var.HIDDEN_AMNESIAC (the new amnesiac is no longer hidden should they die)
    if old_role is not None and evt.data["role"] == "amnesiac" and old_role != "amnesiac":
        evt.data["role"] = ROLES[evt.params.old_player]

@event_listener("new_role")
def on_new_role(evt, var, user, old_role):
    if evt.params.old_player is None and evt.data["role"] == "amnesiac":
        roles = var.ROLE_GUIDE.keys() - _get_blacklist(var)
        ROLES[user] = random.choice(list(roles))

@event_listener("revealing_totem")
def on_revealing_totem(evt, var, votee):
    if evt.data["role"] not in _get_blacklist(var) and not var.HIDDEN_AMNESIAC and len(var.ORIGINAL_ROLES["amnesiac"]):
        global STATS_FLAG
        STATS_FLAG = True
    if evt.data["role"] == "amnesiac":
        votee.send(messages["totem_amnesia_clear"])
        nevt = Event("new_role", {"messages": [], "role": ROLES[votee]}, old_player=None)
        nevt.dispatch(var, votee, "amnesiac")
        evt.data["role"] = nevt.data["role"]
        change_role(votee, "amnesiac", evt.data["role"])
        # If wolfteam, don't bother giving list of wolves since night is about to start anyway
        # Existing wolves also know that someone just joined their team because revealing totem says what they are

@event_listener("get_reveal_role")
def on_reveal_role(evt, var, user):
    if var.HIDDEN_AMNESIAC and var.ORIGINAL_MAIN_ROLES[user] == "amnesiac":
        evt.data["role"] = "amnesiac"

@event_listener("get_endgame_message")
def on_get_endgame_message(evt, var, player, role, is_mainrole):
    if role == "amnesiac":
        # FIXME: Harcoded English
        evt.data["message"].append("would be {0}".format(ROLES[player]))

@event_listener("revealroles_role")
def on_revealroles_role(evt, var, user, role):
    if role == "amnesiac":
        evt.data["special_case"].append("will become {0}".format(ROLES[user]))

@event_listener("update_stats")
def on_update_stats(evt, var, player, mainrole, revealrole, allroles):
    if STATS_FLAG and not _get_blacklist(var) & {mainrole, revealrole}:
        evt.data["possible"].add("amnesiac")

@event_listener("reset")
def on_reset(evt, var):
    global STATS_FLAG
    ROLES.clear()
    STATS_FLAG = False

# vim: set sw=4 expandtab:
