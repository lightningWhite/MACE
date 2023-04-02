# Game Module


class Game:
    """Representation of the game in general"""

    # Note: Not implemented as a 'dataclass' because additional
    # functionality may be added later
    def __init__(
        self,
        name,
        introduction,
        loseConditions,
        winConditions,
        winInteraction,
        loseInteraction,
    ):
        """Constructor

        Parameters
        ----------
        name : string
            The name of the game
        introduction : list of str
            A list of strings representing each sentence that will be displayed
        attributes : map
            Attributes of the game. TODO: Determine if other attributes should be present.
            e.g. over: True
        winConditions : list of str
            Attribute values as strings that will result in a won game
            e.g. player.attributes.hitpoints == 100
        loseConditions : list of str
            Attribute values as strings that will result in game over
            e.g. player.attributes.hitpoints == 0
        winSequence : list of Interaction
            A standard action sequence executed upon win
        loseSequence :  list of Interaction
            A standard action sequence executed upon loss
        """
        self.name = name
        self.introduction = introduction
        self.attributes = {"over": False}
        self.winConditions = winConditions
        self.loseConditions = loseConditions
        self.winSequence = winInteraction
        self.loseSequence = loseInteraction
