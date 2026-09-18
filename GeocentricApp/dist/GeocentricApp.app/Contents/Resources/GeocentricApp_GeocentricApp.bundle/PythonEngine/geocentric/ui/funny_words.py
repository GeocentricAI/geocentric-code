"""Replacements for a boring static 'thinking...' - shown while the model is generating
but hasn't produced any visible text yet. Picked fresh each time a generation phase starts,
so it changes step to step across a turn instead of sitting frozen the whole time.
"""
from __future__ import annotations

import random

FUNNY_WORDS = [
    # pondering, but make it fun
    "pondering", "ruminating", "cogitating", "noodling", "percolating", "marinating",
    "mulling", "deliberating", "contemplating", "brainstorming", "brooding", "musing",
    "deducing", "calculating", "computing", "processing", "reasoning", "philosophizing",
    "hypothesizing", "theorizing", "conjecturing", "speculating", "extrapolating",
    "synthesizing", "digesting", "chewing", "simmering", "stewing", "incubating",
    "gestating", "formulating", "strategizing", "scheming", "plotting", "engineering",
    "architecting", "orchestrating", "choreographing", "calibrating", "triangulating",
    "puzzling", "unraveling", "untangling", "wrangling", "grappling",
    # classic nonsense
    "lollygagging", "bamboozling", "finagling", "shenaniganing", "hornswoggling",
    "skedaddling", "flimflamming", "hobnobbing", "gallivanting", "mollycoddling",
    "canoodling", "dillydallying", "fandangling", "kerfuffling", "discombobulating",
    "rigmaroling", "malarkeying", "poppycocking", "gobbledygooking", "widgetizing",
    "gizmofying", "gadgetsmithing", "whirligigging", "doodading", "flibbertigibbeting",
    "persnicketing", "hootenanning", "shindigging", "hullabalooing", "brouhahaing",
    "ballyhooing", "razzmatazzing", "hooplaing", "bumfuzzling", "flummoxing",
    "hoodwinking", "befuddling", "cattywampusing", "lallygagging", "harrumphing",
    "kerplunking", "whippersnapping", "snickersneeing", "gobbledegooking",
    # cosmic / geocentric flavor
    "orbiting", "stargazing", "epicycling", "moonwalking", "constellating",
    "astro-noodling", "planet-hopping", "comet-chasing", "nebula-diving",
    "wormholing", "stardust-sifting", "satellite-pinging", "telescoping",
    "retrograding", "eclipsing", "equinoxing", "solsticing", "meteor-showering",
    "blackhole-diving", "supernova-ing", "quasar-pulsing", "pulsar-timing",
    "lightspeed-ing", "warp-driving", "hyperspace-jumping", "astro-labbing",
    "celestial-navigating", "zodiac-consulting", "horoscope-reading",
    "ptolemy-consulting", "copernicus-doubting", "epicycle-drawing",
    "spheres-harmonizing", "geocentering", "cosmos-wrangling", "orrery-cranking",
    # coder flavor
    "bit-flipping", "byte-crunching", "semicolon-hunting", "bracket-matching",
    "tab-vs-spacing", "rubber-duck-debugging", "stackoverflow-lurking",
    "cache-warming", "garbage-collecting", "thread-juggling", "pointer-chasing",
    "loop-de-looping", "commit-message-agonizing", "merge-conflict-dodging",
    "yak-shaving", "bikeshedding", "scope-creeping", "tech-debt-accruing",
    "refactor-rabbit-holing", "todo-list-ignoring", "coffee-brewing",
    "keyboard-clacking", "off-by-one-ing", "null-checking", "race-condition-hunting",
    "monkey-patching", "spaghetti-untangling", "bikeshed-painting",
    "linter-appeasing", "type-checker-wrestling", "regex-summoning",
    # more general silliness
    "shilly-shallying", "woolgathering", "daydreaming", "wool-gathering",
    "noodle-scratching", "chin-stroking", "beard-stroking", "gear-turning",
    "cog-spinning", "wheel-greasing", "widget-tinkering", "sprocket-fiddling",
    "abacus-clicking", "slide-rule-sliding", "quill-sharpening", "ink-mixing",
    "candle-burning", "midnight-oil-burning", "elbow-greasing", "sleeve-rolling",
    "gumption-gathering", "moxie-mustering", "chutzpah-channeling",
    "noggin-noodling", "gray-matter-grinding", "synapse-firing", "neuron-tickling",
    "brainwave-surfing", "thought-herding", "idea-wrangling", "notion-noodling",
    "hunch-following", "gut-consulting", "crystal-ball-gazing", "tea-leaf-reading",
    "tarot-shuffling", "magic-8-ball-shaking", "coin-flipping", "dice-rolling",
    "wishbone-snapping", "four-leaf-clover-hunting", "rabbit-foot-rubbing",
    "genie-summoning", "lamp-rubbing", "spell-casting", "potion-brewing",
    "cauldron-stirring", "wand-waving", "incantation-muttering", "rune-carving",
    "oracle-consulting", "sphinx-riddling", "labyrinth-navigating",
    "minotaur-dodging", "hydra-wrangling", "chimera-taming", "phoenix-feeding",
    "dragon-whispering", "griffin-grooming", "kraken-calming", "yeti-tracking",
    "sasquatch-searching", "unicorn-chasing", "narwhal-noodling",
]


def random_funny_word() -> str:
    return random.choice(FUNNY_WORDS)
