# This code allows you to play the classic Even-Odd game against the computer, utilizing the try and except functions for error handling.

import random

def even_odd():
    print("Welcome to the classic Even-Odd game!")

    # User's choice for Even or Odd
    user_choice = input("Enter your choice ('Even' or 'Odd) and see if you can beat the machine: ").lower()

    while user_choice not in ['even', 'odd']:
        print("Invalid choice! Please choose either 'even' or 'odd'.")
        user_choice = input("Enter your choice ('even' or 'odd'): ").lower()
    
    try:
        # User's number choice between 1 and 10
        user_number = int(input("Please choose a whole number between 1 and 10: "))

        while user_number < 1 or user_number > 10:
            print("Your whole number choice is out of range. Please choose a whole number between 1 and 10: ")
            
        # Computer's number choice
        computer_number = random.randint(1, 10)
        total = user_number + computer_number
        
        print(f"You chose {user_number} and the computer chose {computer_number}.")
        print(f"The total is {total}.")
        
        result = 'even' if total % 2 == 0 else 'odd'
        
        # Checking if the user won
        if user_choice == result:
            print(f"Congratulations! The total is {result}, and you won!")
        else:
            print(f"Sorry! The total is {result}, and the computer won.")

    except ValueError as e:
        print(f"Error: {e}")
        
# Running the game
even_odd()       