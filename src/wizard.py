# The Magic and Combat Engine game creation wizard.
#
# This tool makes it easier to create MACE compatible objects and games
# by presenting the user with questions and options in a structured manner.
# Objects in a game are then validated to make sure all referenced objects
# exist.

import os


def presentOptions(options):
    """
    Prints out an indexed list of provided options
    and obtains the user's selection
    param: options - List of tuples containing the option and function
                     to call for that option. e.g. [("option", function())]
    """
    index = 1
    for option in options:
        print(f"\t{index}. {option[0]}")
        index += 1

    invalid = True
    while invalid == True:
        selection = input("\nEnter the number of your choice: ")

        if not selection.isdigit():
            invalid = False
            continue
        selection = int(selection) - 1

        if selection > -1 and selection < len(options):
            # Make sure the option tuple has two elements
            if len(options[int(selection)]) == 2:
                if options[int(selection)][1] is not None:
                    # Invoke the option's function
                    options[int(selection)][1]()
            invalid = False
        else:
            print(
                f"\nInvalid selection. Please enter a number from 1 to {len(options)}."
            )
            continue


def clear():
    """
    Cross-platform method for clearing the terminal window.
    """
    os.system("cls" if os.name == "nt" else "clear")


def printBreak():
    """
    Prints a break between question sequences.
    """
    print("\n--------------------------------------------------------------------")


def getInputList():
    """
    Allows the user to enter multiple strings until an empty item is specified.
    ret A list of inputs
    """
    inputs = []
    inputStr = "not empty"
    while len(inputStr) != 0:
        inputStr = input("> ")
        if len(inputStr) > 0:
            inputs.append(inputStr)
    return inputs


def defineConditions():
    """
    Aids the user in defining condition checks.
    It allows the user to look up other existing components, select
    attributes/subattributes of the component, and define the
    boolean operator to use, and the value to compare against.
    ret: The list of condition strings
    """
    print(
        """
Conditions should be specified in the following form:

<componentId.attribute> <booleanOperator> <value>

For example:

player.hitpoints.current == 0

Multiple conditions can be specified by pressing enter between each one.
"""
    )
    # TODO: Present the user with a list of
    # components that they can choose from, and then select the
    # attribute of that component and what the value should be

    # Ask if main character, interactive element, game, or environment

    # If character, list the attributes
    # Allow an attribute to be selected
    # Repeat (drill down) until they select the one they want
    # Ask for a desired value

    # Do similar things for the other game components

    return getInputList()


def getYesNo():
    """
    Accepts and validates answers given to Yes/No questions.
    It will check various forms or yes/no, and return
    True for yes and False for no. If an invalid response
    is given, it will reprompt.
    ret: Boolean
    """
    while True:
        answer = input("> ")
        if len(answer) > 0:
            # Allow the user to enter 'yes' or 'no' in various forms
            lower_ans = answer.lower()
            if lower_ans[0] == "y":
                return True
            elif lower_ans[0] == "n":
                return False
            else:
                print("Invalid response. Please enter 'y' for yes, or 'n' for no.")
        else:
            print("Invalid response. Please enter 'y' for yes, or 'n' for no.")


def createAction(winLoseAction=False):
    """
    Aids the user in creating action sequences.
    param: winLoseAction - if the action is being created
           for a win/lose action sequence. If True, the visible
           field won't be presented as an option, and it will
           default to a value of 'True'.
    ret: An action sequence object
    """
    if winLoseAction:
        # For win/lose sequences, we always want the action to be visible
        visible = True
        # The action and conditions will just be executed, so leave blank
        description = ""
        conditions = ""
    else:
        valid = False
        while not invalid:
            print(
                "Do you want this action to be visible to the user at the beginning of the game (y/n)?\n> "
            )
            # visible will be true if the answer was 'yes' or 'y' or 'Y' etc.
            visible = getYesNo()
        clear()

        print(
            """
Enter a word or sentence that presents this action as an option.
For example, "Talk to the blacksmith?", or "Open the door?".
Note that if this will be the only available action for the interactive element,
you can leave this blank to just execute the action.

        """
        )
        description = input("> ")
        clear()

        print(
            """
Now define the conditions that must be met for this action to proceed
if selected.
        """
        )
        conditions = defineConditions()
        clear()

    print(
        """Now, write up the dialog sentences that should be displayed to the player when this
sequence is encountered. If you want a pause between sentences displayed to the
player, simply hit enter after a sentence or sentences. This will allow the
player to press enter to continue to the next sentence.
When you're done writing the dialog, press enter with an empty sentence.
"""
    )
    dialog = getInputList()
    clear()

    print(
        """

"""
    )

    # TODO:
    # Modifiers
    # nextActions
    # fallbacks
    return ""


def createSummary():
    """
    Sequence to help user create game objectives and summary.
    """
    clear()
    print("Overarching Game Setting Creation\n")

    # Get the game name
    name = input("What would you like your game to be named?\n> ")
    clear()

    # Get the list of introduction sentences
    print(
        """
Now, write up the introduction sentences that should be displayed to the player
when beginning the game. If you want a pause between sentences displayed to the
player, simply hit enter after a sentence or sentences. This will allow the
player to press enter to continue to the next portion of the introduction.
When you're done writing the introduction, press enter with an empty sentence.
    """
    )
    introduction = getInputList()
    clear()

    # Get the list of conditions defining a loss
    print(
        """Great work!

Now it's time to specify what conditions will result in a lost game.
Specify any attribute values that you want checked between each turn
to determine if the game was lost.
        """
    )

    loseConditions = defineConditions()
    clear()

    # Get the list of conditions defining a win
    print("Now the win conditions need to be specified in the same way.")
    winConditions = defineConditions()
    clear()

    # TODO: Configure the win sequence
    # This will probably best be done by creating an 'action' creation function
    winSequence = createAction(winLoseAction=True)
    clear()

    # TODO: Configure the lose sequence
    # This will probably best be done by creating an 'action' creation function
    loseSequence = createAction(winLoseAction=True)
    clear()


def createGame():
    """
    Aids the user in creating a MACE compatible game.
    """

    clear()
    print(
        """This wizard will help you create the necessary components for a full MACE game.
You will be presented with a series of questions for which you will provide the answers.
You will be able to go back and edit any component at any time during the creation process.

The following component types will be created/configured as part of this wizard:

- The game summary and win/lose conditions
- The game map
- Environment conditions
- Interactive elements
- Which attributes of the player are customizable

Keep in mind that as you go through the creation of each component, if you aren't sure
about something, you can just come back to it later once more of the game is built out.
    """
    )

    wizOptions = [
        ("The game summary and win/lose conditions", createSummary),
        ("The game map", None),
        ("Environment conditions", None),
        ("Interactive elements", None),
        ("Which attributes of the player are customizable", None),
        ("Save and Quit", None),
    ]

    done = False
    while not done:
        print("What would you like to work on now?\n")

        presentOptions(wizOptions)

        print("Do you want to continue editing this game?")
        answer = getYesNo()
        done = not answer
        clear()


def editGame():
    print("\nThis feature is not implemented yet, but will be coming soon!\n")


def startWizard():
    """
    Presents the MACE wizard to the user.
    """
    print("Welcome to the MACE Wizard!")
    print("This tool will help you create or edit a MACE compatible game.")

    options = [
        ("Create a new game", createGame),
        ("Edit an existing game", editGame),
    ]

    done = False
    while not done:
        print("\nWhat would you like to do?\n")
        presentOptions(options)

        print("Do you want to exit the wizard?")
        done = getYesNo()


def main():
    startWizard()


if __name__ == "__main__":
    main()
