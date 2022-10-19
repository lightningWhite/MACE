# The Magic and Combat Engine game creation wizard.
#
# This tool makes it easier to create MACE compatible objects and games
# by presenting the user with questions and options in a structured manner.
# Objects in a game are then validated to make sure all referenced objects
# exist.


def presentOptions(options):
    """
    Prints out an indexed list of provided options
    and obtains the user's selection
    param: options - List of options
    return: The index of the selected option in the list
    """
    index = 1
    for option in options:
        print(f"\t{index}. {option}")
        index += 1

    invalid = True
    while invalid == True:
        selection = input("\nEnter the number of your choice: ")
        if (
            selection.isdigit()
            and int(selection) > 0
            and int(selection) <= len(options)
        ):
            selection = int(selection)
            invalid = False
        else:
            print(
                f"\nInvalid selection. Please enter a number from 1 to {len(options)}."
            )
            continue

    return selection - 1


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
            lower_ans = answer.lower
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
        printBreak()

        print(
            """
Enter a word or sentence that presents this action as an option.
For example, "Talk to the blacksmith?", or "Open the door?".
Note that if this will be the only available action for the interactive element,
you can leave this blank to just execute the action.

        """
        )
        description = input("> ")
        printBreak()

        print(
            """
Now define the conditions that must be met for this action to proceed
if selected.
        """
        )
        conditions = defineConditions()
        printBreak()

    print(
        """
Now, write up the dialog sentences that should be displayed to the player when this
sequence is encountered. If you want a pause between sentences displayed to the
player, simply hit enter after a sentence or sentences. This will allow the
player to press enter to continue to the next sentence.
When you're done writing the dialog, press enter with an empty sentence.
"""
    )
    dialog = getInputList()
    printBreak()

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
    printBreak()
    print("Overarching Game Setting Creation\n")
    name = input("What would you like your game to be named?\n> ")
    printBreak()

    print(
        """
Now, write up the sentences that should be displayed to the player when
beginning the game. If you want a pause between sentences displayed to the
player, simply hit enter after a sentence or sentences. This will allow the
player to press enter to continue to the next introduction portion.
When you're done writing the introduction, press enter with an empty sentence.
    """
    )
    introduction = getInputList()
    printBreak()

    print(
        """
Great work!

Now it's time to specify what conditions will result in a lost game.
Specify any attribute values that you want checked between each turn
to determine if the game was lost.
        """
    )

    loseConditions = defineConditions()
    printBreak()

    print(
        """

Now the win conditions need to be specified in the same way.
        """
    )
    winConditions = defineConditions()
    printBreak()

    # TODO: Configure the win sequence
    # This will probably best be done by creating an 'action' creation function
    winSequence = createAction(winLoseAction=True)
    printBreak()

    # TODO: Configure the lose sequence
    # This will probably best be done by creating an 'action' creation function
    loseSequence = createAction(winLoseAction=True)
    printBreak()


def createGame():
    """
    Aids the user in creating a MACE compatible game.
    """
    print(
        """

This wizard will help you create the necessary components for a full MACE game.
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

    done = False
    while not done:
        print("What would you like to work on now?\n")
        wizOptions = [
            "The game summary and win/lose conditions",
            "The game map",
            "Environment conditions",
            "Interactive elements",
            "Which attributes of the player are customizable",
            "Save and Quit",
        ]
        selection = presentOptions(wizOptions)

        if wizOptions[selection] == wizOptions[0]:
            createSummary()
        elif wizOptions[selection] == wizOptions[1]:
            continue
        elif wizOptions[selection] == wizOptions[2]:
            continue
        elif wizOptions[selection] == wizOptions[3]:
            continue
        elif wizOptions[selection] == wizOptions[4]:
            continue
        elif wizOptions[selection] == wizOptions[5]:
            done = True


def editGame():
    print("\nThis feature is not implemented yet, but will be coming soon!\n")


def startWizard():
    """
    Presents the MACE wizard to the user.
    """
    print("Welcome to the MACE Wizard!")
    print("This tool will help you create or edit a MACE compatible game.")
    print("\nWhat would you like to do?\n")

    options = ["Create a new game", "Edit an existing game"]

    selection = options[presentOptions(options)]

    if selection == options[0]:
        createGame()
    else:
        editGame()


def main():
    startWizard()


if __name__ == "__main__":
    main()
