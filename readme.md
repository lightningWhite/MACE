# MACE - Magic and Combat Environment

Magic and Combat Environment is a Dungeons and Dragons-like game creation wizard and engine for creating and playing D&D-like games defined by YAML files.
The idea is that maps, characters, objects, objectives, and more can be defined in a series of YAML files through the use of the game creation wizard, and then loaded and presented to the user as a Dungeons and Dragons-like game through text-based interactions.

## Development

To begin development on this project, perform the following steps:

1. Clone the repository:
   ```bash
   git clone git@github.com:lightningWhite/MACE.git
   ```
1. Create a Python 3 virtual environment within the cloned repo directory:
   ```bash
   apt install python3-venv
   python3 -m venv env
   ```
1. Activate the virtual environment and install the required packages:
   ```bash
   source env/bin/activate
   pip3 install --upgrade pip
   pip install -r requirements.txt
   ```
1. Run the following for pre-commit checks:
   ```bash
   pre-commit install
   pre-commit run --all-files
   ```

You are now ready to begin developing!
Be sure to activate the environment with `source env/bin/activate` in the terminal you will be running the program in.
To deactivate it when done, simply type `deactivate` in the terminal where it was activated.

## Design

This project consists of several main components:

### Game Creation Wizard

The Game Creation Wizard will present an interactive text-based environment to facilitate the creation of a MACE game.
The wizard will present various categories of the game that need to be defined, and then help the user to define and validate everything.
While users could define everything manually in YAML files, it would be difficult to get all of the needed options correct.
By using the wizard, the user can simply answer the questions, fill out the sections, etc., and the wizard will generate the necessary YAML files that can be read in by the engine to present the game.
Components that will need to be managed by the wizard include the following:

#### Game Objectives and Intro

This is where the user will identify the following:

* The intro summary that will be presented to the player that sets the stage for the quest
* The conditions that define failure
* The conditions that define success
* Other general constraints, such as number of lives

#### World Map

This is where the user will specify the world in which the game will be played.
This includes the following:

* Towns, landmarks, or other locations
* Links between locations
  * This is what determines what directional choices are presented to a player as far as to which destination they want to head
* Intermediary locations
  * These are locations that aren't directly presented to a player, but that are encountered while in transit to a location to which the player is heading (e.g. Troll Bridges, robber ambush spot, etc.)

#### Characters

This is where the user will define the various characters that may be encountered during game play, including the main character.
This includes the following:

* Character name
* Whether the characters is the player or other (only one player can be specified)
* Friend, enemy, or neutral starting stance toward the main player
* Starting location (as defined in the World Map)
* Attributes
  * Hit points
  * Strength
  * Speed
  * Endurance
  * Wisdom
  * Stealth
  * Charisma

#### Objects

This is where the user will define various objects that may be encountered or used throughout the game.
This includes the following:

* Object name
* Where the object is located (as defined in the World Map)
* Obtainment result
  * Possess
  * Reduce health
  * Increase health
TODO: This needs to be defined differently...

#### Environmental Factors

This is where the user will define environmental factors that may be encountered during game play.
This may include things like the following:

* Weather
  * Snow, rain, wind, daytime, nighttime, etc. These may affect the abilities of objects or characters.
* Other
  * Volcanic erruptions, earthquakes, etc.

## TODO Development Notes

This section is used to keep track of things that are in progress or that need to be done.

### Creation Wizard

- [ ] Write classes to represent each of the game components
- [ ] Add YAML support to write out the classes to files
- [ ] Determine individual game config file organization structure
- [ ] Save files to the determined structure when creating a game
- [ ] Load all of the game elements into the Wizard
- [ ] Write a function to allow users to select attributes from the components loaded into the wizard
- [ ] Edit previously created games
- [ ] Finish writing the wizard function to create a game action
- [ ] Implement the wizard section for creating the map
- [ ] Implement the wizard section for creating the environment conditions
- [ ] Implement the wizard section for creating the interactive elements
- [ ] Implement the wizard section for configuring the main character
- [ ] Implement some sort of validation to make sure referenced items exist

### Game Engine

- [ ] Design how this will work
