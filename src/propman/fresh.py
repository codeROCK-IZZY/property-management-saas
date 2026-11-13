"""Phrasings written after the freeze commit (74fa0c6), and never used to change the classifier.

They describe the same seventeen kinds of problem in other words, the way different tenants would.
"""

from __future__ import annotations

FRESH: dict[tuple[str, str], list[str]] = {
    ("emergency", "plumbing"): [
        "the ceiling above the bath is bulging and dripping fast",
        "the kitchen floor is ankle deep and it's still coming",
        "the toilet overflowed and it won't stop, it's going under the door",
        "the hot water tank split and the airing cupboard is under water",
    ],
    ("emergency", "electrical"): [
        "the plug socket in the bedroom went bang and is black",
        "the lights are buzzing and there's a smell of hot plastic",
        "everything electrical has gone off and the trip switch keeps flicking back",
        "the extension lead behind the TV melted",
    ],
    ("emergency", "heating"): [
        "it smells like gas in the kitchen and the hob isn't on",
        "the alarm that detects carbon monoxide is going off",
        "the boiler packed up, it's minus five outside and we have a newborn",
        "the flue on the boiler is hissing and there's a strong smell",
    ],
    ("emergency", "locks"): [
        "we got burgled and the door frame is split so it won't shut",
        "I can't get into my flat, my keys were stolen with my bag",
        "the front door won't latch at all and it's the middle of the night",
        "someone tried to force the lock and now it won't close",
    ],
    ("emergency", "general"): [
        "the bathroom ceiling has come down",
        "a car hit the front wall and there are bricks loose",
        "the bedroom window frame fell out in the wind",
        "part of the stairs gave way when I stepped on it",
    ],
    ("urgent", "plumbing"): [
        "the toilet is clogged and it's the only one we have",
        "no hot water since the weekend",
        "the kitchen sink won't drain at all and smells",
        "the shower only runs cold",
    ],
    ("urgent", "electrical"): [
        "the sockets on one side of the living room are dead",
        "every time we use the kettle all the lights go off",
        "the kitchen lights don't work at all",
        "the electric shower won't turn on",
    ],
    ("urgent", "heating"): [
        "the heating won't come on and it's getting cold at night",
        "the boiler keeps cutting out and we have no heat most evenings",
        "the radiators upstairs don't warm up at all",
        "the air con broke and the flat is like an oven",
    ],
    ("urgent", "appliance"): [
        "the fridge has stopped working completely",
        "the cooker won't turn on so we can't make dinner",
        "the washing machine is stuck full of water with our clothes in it",
        "the freezer died and everything is thawing",
    ],
    ("urgent", "locks"): [
        "the back door lock is broken so we can only lock the front",
        "the front door key turns but the lock doesn't catch",
        "the lock on the garden gate snapped",
        "the bedroom window won't close or lock",
    ],
    ("urgent", "general"): [
        "there's a rat in the kitchen",
        "damp patches are spreading on the bedroom wall and the kids are coughing",
        "rainwater is coming in under the back door",
        "the banister is wobbly and my dad nearly fell",
    ],
    ("routine", "plumbing"): [
        "the kitchen tap is a bit loose",
        "the toilet flush is weak",
        "the plug in the bath doesn't hold water",
        "there's a small drip under the bathroom sink into the cupboard",
    ],
    ("routine", "electrical"): [
        "the bathroom pull cord is broken",
        "the security light outside doesn't come on",
        "a couple of spotlights in the kitchen have blown",
        "the TV aerial socket is loose",
    ],
    ("routine", "heating"): [
        "the radiator in the hall needs bleeding",
        "the heating timer is set wrong and I can't change it",
        "the cooker hood fan rattles",
        "the bedroom radiator knob came off",
    ],
    ("routine", "appliance"): [
        "the dishwasher is making a grinding noise",
        "the freezer drawer is cracked",
        "the washing machine door handle broke",
        "the oven light is out",
    ],
    ("routine", "locks"): [
        "can you send a spare key for the shed",
        "the sliding door is hard to lock",
        "the window key is missing",
        "the post box lock is stiff",
    ],
    ("routine", "general"): [
        "the skirting board is coming away in the lounge",
        "the shower screen seal is perished",
        "there's a crack in a bathroom tile",
        "the garden gate is sagging",
    ],
}
