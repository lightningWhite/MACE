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


def createGame():
    print("")
    print(
        "\tThis wizard will help you create the necessary components for a full MACE game."
    )
    print(
        "\tYou will be presented with a series of questions for which you will provide the answers."
    )
    print(
        "\tYou will be able to go back and edit any component at any time during the creation process."
    )
    print("")


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
