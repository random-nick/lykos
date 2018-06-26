import re
import random
import itertools
import math
from collections import defaultdict

import botconfig # for CMD_CHAR only
from src.utilities import *
from src import channels, users, debuglog, errlog, plog
from src.functions import get_players, get_all_players, get_main_role, get_reveal_role, get_target
from src.decorators import command, event_listener
from src.containers import UserList, UserSet, UserDict, DefaultUserDict
from src.messages import messages
from src.events import Event

GUNNERS = UserDict() # type: Dict[users.User, int]

@event_listener("transition_day_resolve_end")
def on_transition_day_resolve_end(evt, var, victims):
    for victim in list(evt.data["dead"]):
        if victim in GUNNERS and GUNNERS[victim] > 0 and victim in evt.data["bywolves"]:
            if random.random() < var.GUNNER_KILLS_WOLF_AT_NIGHT_CHANCE:
                # pick a random wofl to be shot
                woflset = {wolf for wolf in get_players(var.WOLF_ROLES) if wolf not in evt.data["dead"]}
                # TODO: split into werekitten.py
                woflset.difference_update(get_all_players(("werekitten",)))
                wolf_evt = Event("gunner_overnight_kill_wolflist", {"wolves": woflset})
                wolf_evt.dispatch(var)
                woflset = wolf_evt.data["wolves"]
                if woflset:
                    deadwolf = random.choice(tuple(woflset))
                    if var.ROLE_REVEAL in ("on", "team"):
                        evt.data["message"].append(messages["gunner_killed_wolf_overnight"].format(victim, deadwolf, get_reveal_role(deadwolf)))
                    else:
                        evt.data["message"].append(messages["gunner_killed_wolf_overnight_no_reveal"].format(victim, deadwolf))
                    evt.data["dead"].append(deadwolf)
                    evt.data["killers"][deadwolf].append(victim)
                    GUNNERS[victim] -= 1 # deduct the used bullet

    for victim in evt.data["dead"]:
        if victim in evt.data["bywolves"] and victim in var.DISEASED:
            var.DISEASED_WOLVES = True
        if var.WOLF_STEALS_GUN and victim in evt.data["bywolves"] and victim in GUNNERS and GUNNERS[victim] > 0:
            # victim has bullets
            try:
                looters = get_players(var.WOLFCHAT_ROLES)
                while len(looters) > 0:
                    guntaker = random.choice(looters)  # random looter
                    if guntaker not in evt.data["dead"]:
                        break
                    else:
                        looters.remove(guntaker)
                if guntaker not in evt.data["dead"]:
                    numbullets = GUNNERS[victim]
                    if guntaker not in GUNNERS:
                        GUNNERS[guntaker] = 0
                    if guntaker not in get_all_players(("gunner", "sharpshooter")):
                        var.ROLES["gunner"].add(guntaker)
                    GUNNERS[guntaker] += 1  # only transfer one bullet
                    guntaker.send(messages["wolf_gunner"].format(victim))
            except IndexError:
                pass # no wolves to give gun to (they were all killed during night or something)
            GUNNERS[victim] = 0  # just in case

@event_listener("transition_night_end")
def on_transition_night_end(evt, var):
    ps = get_players()
    for g in GUNNERS:
        if g not in ps:
            continue
        elif not GUNNERS[g]:
            continue
        role = "gunner"
        if g in get_all_players(("sharpshooter",)):
            role = "sharpshooter"
        if g.prefers_simple():
            gun_msg = messages["gunner_simple"].format(role, str(GUNNERS[g]), "s" if GUNNERS[g] > 1 else "")
        else:
            if role == "gunner":
                gun_msg = messages["gunner_notify"].format(role, botconfig.CMD_CHAR, str(GUNNERS[g]), "s" if GUNNERS[g] > 1 else "")
            elif role == "sharpshooter":
                gun_msg = messages["sharpshooter_notify"].format(role, botconfig.CMD_CHAR, str(GUNNERS[g]), "s" if GUNNERS[g] > 1 else "")

        g.send(gun_msg)

@event_listener("role_assignment")
def on_role_assignment(evt, var, gamemode, players): # FIXME: This event is removed in the PR, need to fix after merging
    cannot_be_sharpshooter = get_players(var.TEMPLATE_RESTRICTIONS["sharpshooter"]) + list(var.FORCE_ROLES["gunner"])
    gunner_list = set(var.ROLES["gunner"]) # make a copy since we mutate var.ROLES["gunner"]
    num_sharpshooters = 0
    for gunner in gunner_list:
        if gunner in var.ROLES["village drunk"]:
            GUNNERS[gunner] = (var.DRUNK_SHOTS_MULTIPLIER * math.ceil(var.SHOTS_MULTIPLIER * len(pl)))
        elif num_sharpshooters < addroles["sharpshooter"] and gunner not in cannot_be_sharpshooter and random.random() <= var.SHARPSHOOTER_CHANCE:
            GUNNERS[gunner] = math.ceil(var.SHARPSHOOTER_MULTIPLIER * len(pl))
            var.ROLES["gunner"].remove(gunner)
            var.ROLES["sharpshooter"].add(gunner)
            num_sharpshooters += 1
        else:
            GUNNERS[gunner] = math.ceil(var.SHOTS_MULTIPLIER * len(pl))

@event_listener("myrole")
def on_myrole(evt, var, user):
    # Check for gun/bullets
    if user not in var.ROLES["amnesiac"] and wrapper.source in GUNNERS and GUNNERS[user]:
        role = "gunner"
        if user in var.ROLES["sharpshooter"]:
            role = "sharpshooter"
        evt.data["messages"].append(messages["gunner_simple"].format(role, GUNNERS[user], "" if GUNNERS[user] == 1 else "s"))

@event_listener("revealroles_role")
def on_revealroles_role(evt, var, user, role):
    # print how many bullets normal gunners have
    if (role == "gunner" or role == "sharpshooter") and user in GUNNERS:
        evt.data["special_case"].append("{0} bullet{1}".format(GUNNERS[user], "" if GUNNERS[user] == 1 else "s"))
