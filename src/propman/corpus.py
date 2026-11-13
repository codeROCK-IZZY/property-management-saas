"""Synthetic maintenance requests, written the way tenants write them.

Each request has a true urgency (emergency, urgent, routine) and trade (plumbing, electrical, heating, appliance,
locks, general), set by the actual problem rather than by the tenant's tone: some tenants shout "URGENT!!" about a
dripping tap, others apologise for bothering anyone while water comes through the ceiling. Messages mix a greeting,
the problem in one of several phrasings, where and since when, and sometimes a worry or an apology, with the odd
lower-case or exclamation-heavy writer.

`TEMPLATES` holds the phrasings written before the classifier was built: the first four of each kind are used for
tuning and the rest are held out. `FRESH`, in fresh.py, holds phrasings written after the classifier was frozen.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

URGENCIES = ("emergency", "urgent", "routine")
TRADES = ("plumbing", "electrical", "heating", "appliance", "locks", "general")

# Phrasings per kind of problem. The first four of each are the tuning phrasings; the rest are held out, so the
# held-out bank tests wording the classifier never saw, not just new tenants using the same sentences.
TEMPLATES: dict[tuple[str, str], list[str]] = {
    ("emergency", "plumbing"): [
        "water is pouring through the ceiling",
        "a pipe burst under the sink and the kitchen is flooding",
        "sewage is coming back up through the bath drain",
        "the water heater is gushing water everywhere",
        "there's water spraying from the wall behind the toilet",
        "the flat below says water is dripping into their lights",
        "the stopcock won't turn off and water keeps rising",
    ],
    ("emergency", "electrical"): [
        "sparks came out of the socket when I plugged in the kettle",
        "there's a burning smell from the light switch",
        "the whole flat has no power and the breaker won't reset",
        "wires are hanging out of the wall and buzzing",
        "the fuse box is smoking",
        "a socket is scorched black and hot to touch",
    ],
    ("emergency", "heating"): [
        "I can smell gas near the boiler",
        "the carbon monoxide alarm keeps going off",
        "we have no heating at all and it's below freezing",
        "the boiler is making a banging noise and smells of gas",
        "there's a smell like rotten eggs by the cooker",
        "the CO detector is beeping and we feel dizzy",
    ],
    ("emergency", "locks"): [
        "I'm locked out and it's late at night",
        "the front door was kicked in and won't close",
        "the main door lock is broken and the flat can't be secured",
        "someone broke the lock while we were away",
        "the building entrance door won't lock and strangers are coming in",
        "my key broke off in the front door and I can't get in",
    ],
    ("emergency", "general"): [
        "part of the bedroom ceiling just collapsed",
        "the living room window was smashed and there's glass everywhere",
        "a tree branch came through the roof",
        "the balcony railing fell off",
        "a big crack opened in the wall and plaster is falling",
        "the storm ripped part of the roof off",
    ],
    ("urgent", "plumbing"): [
        "our only toilet won't flush",
        "there's no hot water at all",
        "the kitchen drain is completely blocked",
        "the shower drain backs up every time",
        "the water pressure dropped to a trickle",
        "the toilet is leaking at the base",
    ],
    ("urgent", "electrical"): [
        "half the sockets in the kitchen stopped working",
        "the lights keep flickering in every room",
        "the oven circuit keeps tripping",
        "the bathroom light and fan both died",
        "the power keeps cutting out for a few seconds",
        "none of the bedroom sockets work",
    ],
    ("urgent", "heating"): [
        "the heating only works in one room",
        "the air conditioning stopped working in this heatwave",
        "the radiators are stone cold in the bedrooms",
        "the boiler keeps losing pressure",
        "the heating comes on for ten minutes then cuts out",
        "the boiler shows an error code and won't start",
    ],
    ("urgent", "appliance"): [
        "the fridge isn't cooling and the food is going off",
        "the oven won't heat up",
        "the washing machine leaks a puddle every wash",
        "the freezer is defrosting",
        "the hob rings won't light",
        "the fridge is warm inside",
    ],
    ("urgent", "locks"): [
        "the key snapped in the back door lock",
        "the front door lock is very stiff and hard to turn",
        "the patio door won't lock",
        "the deadbolt on the front door is jammed",
        "the back door won't close properly any more",
        "the window lock in the ground floor bedroom is broken",
    ],
    ("urgent", "general"): [
        "black mould is spreading across the bathroom ceiling",
        "we've seen mice in the kitchen",
        "the stair handrail came loose",
        "there are cockroaches in the cupboards",
        "rain is getting in around the window frame",
        "a floorboard has given way in the hall",
    ],
    ("routine", "plumbing"): [
        "the bathroom tap drips",
        "the toilet keeps running after flushing",
        "the sink drains slowly",
        "the shower head is clogged with limescale",
        "the bath sealant is going mouldy",
        "the toilet seat is loose",
    ],
    ("routine", "electrical"): [
        "the hallway light bulb needs replacing",
        "the doorbell doesn't ring",
        "one bulb in the kitchen is out",
        "a light switch cover is cracked",
        "the outside light stays on all day",
        "the smoke alarm battery chirps",
    ],
    ("routine", "heating"): [
        "the radiator in the lounge makes a ticking noise",
        "the thermostat display is faded",
        "the bathroom extractor fan is noisy",
        "a radiator valve is stiff",
        "the boiler is due its annual service",
        "one radiator is a bit cooler at the top",
    ],
    ("routine", "appliance"): [
        "the dishwasher doesn't dry properly",
        "the microwave light has gone",
        "the fridge door seal is a bit loose",
        "the tumble dryer takes ages",
        "the oven clock is wrong and won't reset",
        "the cooker hood light is broken",
    ],
    ("routine", "locks"): [
        "I lost the mailbox key",
        "the window latch in the bedroom is loose",
        "can I get a spare key cut",
        "the bike store padlock is rusty",
        "the letterbox flap sticks",
        "the garage door key is hard to turn",
    ],
    ("routine", "general"): [
        "the paint is peeling in the hallway",
        "a kitchen cupboard door hinge is broken",
        "the bedroom door squeaks",
        "a few fence panels are leaning",
        "the carpet on the stairs is fraying",
        "the curtain rail came away from the wall",
    ],
}
TUNING_PHRASINGS = 4


def split(templates: dict[tuple[str, str], list[str]], part: str) -> dict[tuple[str, str], list[str]]:
    """The tuning phrasings (`"tuning"`) or the held-out ones (`"heldout"`) of each kind."""
    return {k: (v[:TUNING_PHRASINGS] if part == "tuning" else v[TUNING_PHRASINGS:]) for k, v in templates.items()}


GREET = ["Hi,", "Hello,", "Hi there,", "Good morning,", "", "", "Hey,"]
WHEN = ["since this morning", "since yesterday", "for a few days now", "just now", "since last night", "", ""]
WHERE = ["", "in the kitchen", "upstairs", "in flat 4B", "", "in the bathroom"]
CALM = ["Not sure if this is a big deal, but", "Sorry to bother you, but", "No rush, but", "When you get a chance:"]
LOUD = ["URGENT!!", "Please help ASAP!", "This is unacceptable,", "Need someone TODAY,", "EMERGENCY:"]
WORRY = ["We have a baby at home.", "My mum is elderly and lives with us.", "I work from home.", "", "", ""]
SIGN = ["Thanks", "Thank you!", "Cheers", "Regards, tenant", "", ""]


@dataclass(frozen=True)
class Request:
    text: str
    urgency: str
    trade: str
    phrasing: int = 0  # which phrasing of its kind, so cross-validation can hold whole phrasings out


def generate(n: int, seed: int, templates: dict[tuple[str, str], list[str]] = TEMPLATES) -> list[Request]:
    """`n` requests; emergencies are rarer than routine jobs, as in real portfolios."""
    g = np.random.default_rng(seed)
    keys = sorted(templates)
    weight = np.array([{"emergency": 0.3, "urgent": 1.0, "routine": 1.4}[k[0]] for k in keys])
    out = []
    for _ in range(n):
        k = keys[int(g.choice(len(keys), p=weight / weight.sum()))]
        j = int(g.integers(len(templates[k])))
        problem = templates[k][j]
        tone = float(g.random())
        lead = (
            CALM[int(g.integers(len(CALM)))] if tone < 0.2 else LOUD[int(g.integers(len(LOUD)))] if tone > 0.85 else ""
        )
        parts = [
            GREET[int(g.integers(len(GREET)))],
            lead,
            problem,
            WHERE[int(g.integers(len(WHERE)))],
            WHEN[int(g.integers(len(WHEN)))] + ".",
            WORRY[int(g.integers(len(WORRY)))],
            SIGN[int(g.integers(len(SIGN)))],
        ]
        text = " ".join(p for p in parts if p).replace(" .", ".")
        if g.random() < 0.15:
            text = text.lower()
        if g.random() < 0.1:
            text = text.replace(".", "!!", 1)
        out.append(Request(text, k[0], k[1], j))
    return out
