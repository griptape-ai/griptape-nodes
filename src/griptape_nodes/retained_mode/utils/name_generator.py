"""Generates random fun names for engines like 'admirable-finch' or 'ancient-green-cat'.

Used for default engine naming when no custom name is provided.
"""

import random

ADJECTIVES = [
    "admirable",
    "ancient",
    "brave",
    "bright",
    "calm",
    "clever",
    "cool",
    "cozy",
    "daring",
    "dreamy",
    "eager",
    "elegant",
    "epic",
    "fancy",
    "fierce",
    "fluffy",
    "gentle",
    "golden",
    "graceful",
    "happy",
    "honest",
    "jolly",
    "kind",
    "lively",
    "lucky",
    "magical",
    "mighty",
    "noble",
    "peaceful",
    "playful",
    "proud",
    "quiet",
    "radiant",
    "serene",
    "shiny",
    "silver",
    "smooth",
    "stellar",
    "swift",
    "tender",
    "valiant",
    "vibrant",
    "warm",
    "wise",
    "wonderful",
    "zesty",
]

ANIMALS = [
    "ant",
    "bear",
    "cat",
    "deer",
    "eagle",
    "finch",
    "goat",
    "hawk",
    "ibis",
    "jay",
    "kiwi",
    "llama",
    "mouse",
    "newt",
    "owl",
    "panda",
    "quail",
    "rabbit",
    "seal",
    "tiger",
    "urchin",
    "viper",
    "whale",
    "xerus",
    "yak",
    "zebra",
    "badger",
    "crane",
    "dove",
    "elk",
    "fox",
    "gecko",
    "heron",
    "iguana",
    "jackal",
    "koala",
    "lynx",
    "mole",
    "narwhal",
    "otter",
    "penguin",
    "quokka",
    "raven",
    "swan",
    "turtle",
    "unicorn",
    "vulture",
    "wolf",
    "xenops",
    "yellowhammer",
]

COLORS = [
    "amber",
    "azure",
    "bronze",
    "coral",
    "crimson",
    "emerald",
    "forest",
    "golden",
    "indigo",
    "jade",
    "lavender",
    "magenta",
    "navy",
    "orange",
    "pink",
    "rose",
    "ruby",
    "sage",
    "teal",
    "violet",
    "white",
    "yellow",
    "black",
    "blue",
    "brown",
    "cyan",
    "gray",
    "green",
    "lime",
    "maroon",
    "olive",
    "purple",
    "red",
    "silver",
]


def generate_engine_name() -> str:
    """Generate a random engine name in the format 'adjective-animal' or 'adjective-color-animal'.

    Returns:
        str: A randomly generated engine name
    """
    adjective = random.choice(ADJECTIVES)  # noqa: S311
    animal = random.choice(ANIMALS)  # noqa: S311

    # 30% chance to include a color for more variety
    color_chance = 0.3
    if random.random() < color_chance:  # noqa: S311
        color = random.choice(COLORS)  # noqa: S311
        return f"{adjective}-{color}-{animal}"
    return f"{adjective}-{animal}"
