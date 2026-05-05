# The Fibonacci numbers

# Defining the function with 2 variables (start: initial number; count: how many terms the user would like to see)
def fibonacci_sequence(start, count):
    # Starting the sequence with the first two numbers as a list
    fib_sequence = []

    # Validating the first number
    if start == 0:
        fib_sequence = [0, 1]
    elif start == 1:
        fib_sequence = [1, 1]
    else:
        a, b = 0, 1
        # Finding the Fibonacci number closest to the starting point
        while b < start:
            a, b = b, a + b
        fib_sequence = [b, a + b]

    # Generating the sequence until reaching the desired count
    while len(fib_sequence) < count:
        fib_sequence.append(fib_sequence[-1] + fib_sequence[-2])

    return fib_sequence


# Asking the user to input the start number and how many terms to display
start = int(input("Please enter the initial number for the Fibonacci sequence: "))
count = int(input("How many numbers in the Fibonacci sequence would you like to see? "))

# Displaying the Fibonacci sequence
sequence = fibonacci_sequence(start, count)
print(f"The Fibonacci sequence starting from {start} is: {sequence}")