# Interaction Module


class Interaction:
    """
    Representation of an Interaction

    This allows options to be presented to the user
    based on present game conditions. These can modify
    the game state based on action invocation or based
    on the player's selection. Interactions can also be
    chained together, and can branch according to input
    or conditions.
    """

    # Note: Not implemented as a 'dataclass' because additional
    # functionality may be added later
    def __init__(
        self,
        visible,
        description,
        conditions,
        dialog,
        modifiers,
        nextInteractions,
        fallbacks,
    ):
        """Constructor

        Parameters
        ----------
        visible : boolean
            Whether the action should be presented to the player
        description : str
            What is presented to the player as the option,
            or general info about the element. This can be
            left blank to simply execute the action, rather than
            ask the player if they want to perform the action
            as described in this field. This is presented before
            the conditions are checked.
        conditions : list of str
            Game states that must be true for the dialog, modifiers,
            and subsequent actions to be performed. If any of the
            conditions evaluate to false, the fallback action will
            be invoked. This can be left empty if the action should
            just be performed.
        dialog : list of str
            List of sentences that will be presented to the user
            one by one if the conditions are met
        modifiers : list of str
            List elements and their attributes to modify, and how
            they should be modified. This field can be left empty.
            Modifer strings are of the following format:
            "<componentId.attribute>: <value>"
            <value> can be +<amount>, -<amount>, <value>, or
            '<reference to another attribute's value>'
            This allows attributes to be incremented, decremented,
            assigned, or set to another attribute's value.
            If the string's value is '_attack_', this is a special
            keyword to invoke combat mode.
        nextInteractions : list of Interaction
            A list of Interactions to present once this action is selected
            and if the conditions were met. This allows for Interaction
            chaining.
        fallbacks :  list of Interaction
            A list of Interactions to present once this action is selected
            if the conditions were NOT met. This allows for Interaction
            chaining and branching.
        """
        self.visible = visible
        self.description = description
        self.conditions = conditions
        self.dialog = dialog
        self.modifiers = modifiers
        self.nextInteractions = nextInteractions
        self.fallbacks = fallbacks
