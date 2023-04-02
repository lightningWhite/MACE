# The Magic and Combat Engine game creation wizard.
#
# This tool makes it easier to create MACE compatible objects and games
# by presenting the user with questions and options in a structured manner.
# Objects in a game are then validated to make sure all referenced objects
# exist.

import os
import yaml
import modules.objects.game as game
import modules.objects.interaction as interaction


def presentOptions(options):
    """
    Prints out an indexed list of provided options
    and obtains the user's selection
    param: options - List of option strings
                     e.g. ["option"]
    """
    index = 1
    for option in options:
        print(f"\t{index}. {option}")
        index += 1

    while True:
        selection = input("\nEnter the number of your choice: ")

        if (
            selection.isdigit()
            and int(selection) > 0
            and int(selection) <= len(options)
        ):
            return int(selection)
        else:
            print(
                f"\nInvalid selection. Please enter a number from 1 to {len(options)}."
            )


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

player.location == castle

Multiple conditions can be specified by pressing enter between each one.

Note: This will be made easier for the user in the future by
presenting a list of available attributes the user can select.
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


def createWinLoseInteraction():
    """
    Aids the user in creating win/lose interaction sequences.
    The instructions for creating a win/lose interaction are a bit different
    than those for regular interactions, so this makes it more specific.

    return : Interaction
        The populated Interaction object
    """
    # We want to skip right to the dialog when winning or losing
    visible = True
    description = ""
    conditions = ""

    print(
        """Write up the dialog sentences that should be displayed to the player.
If you want a pause between blocks of text displayed to the player, simply hit
enter. This will allow the player to press enter to continue to the next
sentence. When you're done writing the dialog, press enter with an empty
sentence.
"""
    )
    dialog = getInputList()
    clear()

    # Skip the modifiers for win/lose
    modifiers = []

    # Get the nextInteractions if the conditions were met
    print(
        """Additional options?

Once the player has finished the game, if you want to present
some additional options, such as "Play again?" or something, we can
create those now. The next set of instructions from the wizard will
direct you through creating one or more standard options. As you follow
the instructions for creating a standard option, keep in mind you can
leave some of the fields blank if they don't apply.
"""
    )
    nextInteractions = []
    another = True
    while another:
        print(
            f"Do you want to present another option after the user has finished the game?"
        )
        another = getYesNo()
        if another:
            newInteraction = createInteraction()
            nextInteractions.append(newInteraction)
    clear()

    # Fallbacks aren't used for win/lose
    fallbacks = []

    createdInteraction = interaction.Interaction(
        visible, description, conditions, dialog, modifiers, nextInteractions, fallbacks
    )

    return createdInteraction


def createInteraction():
    """
    Aids the user in creating interactions.
    An interaction can be a simple option, or it can directly
    modify the game state.
    return : Interaction
        The populated Interaction object
    """
    print("Do you want this option to start out as visible to the user? (y/n)?\n> ")
    # visible will be true if the answer was 'yes' or 'y' or 'Y' etc.
    visible = getYesNo()
    clear()

    # Get the description
    print(
        """ Write the option

Enter a word or sentence that presents this interaction as an option.
For example, "Talk to the blacksmith?", or "Open the door?".
Note that if this will be the only available action for the interactive element,
you can leave this blank to just execute the action.

    """
    )
    description = input("> ")
    clear()

    # Get the conditions
    print(
        """Define the conditions to execute the action

Now define the conditions that must be met for the changes defined in this
action to take place. These conditions must also be met for the next
options to be presented. Otherwise, the fallback actions, if any, will be
presented instead.
      """
    )
    conditions = defineConditions()
    clear()

    # Get the dialog
    print(
        """Write the dialog

Now, write up the dialog sentences that should be displayed to the player when
this option is selected and the conditions ARE met. If you want a pause between
blocks of text displayed to the player, simply hit enter. This will allow the
player to press enter to continue to the next sentence. When you're done writing
the dialog, press enter with an empty sentence. You can leave this blank if dialog
doesn't make sense here.
"""
    )
    dialog = getInputList()
    clear()

    # Get the modifiers
    print(
        """Define the modifiers

Now it's time to establish what should happen when this action
is selected and the conditions are met. This involves changing
attributes of elements in the game to change the game state.
For example, if the option was "Open the chest?", then the chest
likely has an attribute named 'isOpen' that needs to be set
to True once this action is performed.

Specify the attributes that need to be modified in one of the
following ways:

- Set an attribute to a value:
  <componentId.attribute>: <value>

- Increment an attribute by an amount:
  <componentId.attribute>: +<amount>

- Decrement an attribute by an amount:
  <componentId.attribute>: -<amount>

- Set the value of an attribute to the value of another attribute:
  <componentId.attribute>: <componentId.attribute>
"""
    )
    modifiers = getInputList()
    clear()

    # Get the nextInteractions if the conditions were met
    print(
        """Create the next interactions

Now we need to define any additional options that should be
presented to the user that should follow the previous action.
For example, if you opened a chest, maybe you now want to ask
the user if they want to pick up the potion inside. To create
a subsequent action, we'll repeat the same steps, once for each
additional option you want to present.
"""
    )
    nextInteractions = []
    another = True
    while another:
        print(
            f"Do you want to present a subsequent action to the '{description}' option?"
        )
        another = getYesNo()
        if another:
            newInteraction = createInteraction()
            nextInteractions.append(newInteraction)
    clear()

    # Get the fallback actions for if the conditions weren't met
    print(
        """Define the fallback interactions

We're almost done with this interaction! Now that we've defined what should
happen if the conditions were met for the '{description}' option, we
need to define any subsequent options that should be presented to the
user if the conditions weren't met. For example, maybe they selected
"Open the chest", but one of the required conditions was that the
chest must be unlocked. Perhaps in this case, you'd want to present
an option to "Try picking the lock". To create a subsequent fallback
option, we'll again repeat the same steps, once for each additional
fallback option you want to present.
"""
    )
    fallbacks = []
    another = True
    while another:
        print(
            f"Do you want to present a subsequent action to the '{description}' option?"
        )
        another = getYesNo()
        if another:
            newInteraction = createInteraction()
            fallbacks.append(newInteraction)

    print("About to construct the action")
    createdInteraction = interaction.Interaction(
        visible, description, conditions, dialog, modifiers, nextInteractions, fallbacks
    )
    clear()

    return createdInteraction


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
        """Write the introduction

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
        """Define the lose conditions

Great work!

Now it's time to specify what conditions will result in a lost game.
Specify any attribute values that you want checked between each turn
to determine if the game was lost.
        """
    )
    loseConditions = defineConditions()
    clear()

    # Get the list of conditions defining a win
    print("Define the win conditions\n")
    print("Now the win conditions need to be specified in the same way.")
    winConditions = defineConditions()
    clear()

    # Configure the win action
    print("Write the win dialog\n")
    print("Now we're going to create the sequence for when the player wins the game.")
    winInteraction = createWinLoseInteraction()
    clear()

    # Configure the lose action
    print("Write the lose dialog\n")
    print("Now we're going to create the sequence for when the player loses the game.")
    loseInteraction = createWinLoseInteraction()
    clear()

    gameObj = game.Game(
        name,
        introduction,
        loseConditions,
        winConditions,
        winInteraction,
        loseInteraction,
    )
    return gameObj


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

    gameObj = game.Game()

    wizOptions = [
        "The game summary and win/lose conditions",
        "The game map",
        "Environment conditions",
        "Interactive elements",
        "Which attributes of the player are customizable",
        "Save and Quit",
    ]

    done = False
    while not done:
        print("What would you like to work on now?\n")

        selection = presentOptions(wizOptions)
        if selection == 1:
            gameObj = createSummary()
            # TODO: Write the game object to a file
            # and establish/follow the directory structure
            # for the game files
            print(f"Here's the Game Summary:\n {yaml.dump(gameObj)}")
        elif selection == 2:
            pass
        elif selection == 3:
            pass
        elif selection == 4:
            pass
        elif selection == 5:
            pass
        elif selection == 6:
            pass
        else:
            print("Unknown selection")

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
    clear()
    print("Welcome to the MACE Wizard!")
    print("This tool will help you create or edit a MACE compatible game.")

    options = [
        "Create a new game",
        "Edit an existing game",
    ]

    done = False
    while not done:
        print("\nWhat would you like to do?\n")
        selection = presentOptions(options)
        if selection == 1:
            createGame()
        elif selection == 2:
            editGame()
        else:
            print("Unknown selection")

        print("Do you want to exit the wizard?")
        done = getYesNo()
    clear()


def main():
    startWizard()


if __name__ == "__main__":
    main()
