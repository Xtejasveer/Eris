# Opening
Good morning, everyone. Mr. Nair is at a coding teachers' training day today, so I am your substitute. He asked me to pass on one message: after class, type each program yourself and change the numbers to see what happens. Today we learn the while loop. Here is a question to keep in your head: how would you print the numbers 1 to 10 without writing ten print lines?

# Syntax of a while loop with its indented body
Think of stirring a sauce. You keep stirring until it thickens. You do not write "stir" a hundred times in a list. A loop does the same job in code: it repeats a piece of code for us.
In Python, a while loop starts with the word while, then a condition, then a colon. The condition is a question that is either True or False.
NOTE: Writing a while loop
- while condition:
- body: the indented lines, run again and again
- first line not indented: runs after the loop
END
The lines indented under the while line are the body. Python uses that indentation to know what belongs to the loop. Let's see a tiny one.
CODE hello_loop.py
count = 1
while count <= 3:
    print(count)
    count = count + 1
print("done")
END
Before I run it, what do you think it prints?
OUTPUT
1
2
3
done
END
The terminal output matches what we expected. The three counts came out one per line, and the word done came last, after the loop had finished. Let's go on.

# The condition is checked before every pass
A loop needs to know when to stop, and the condition decides that. Think of sipping a cup of tea. You keep sipping while there is still tea in the cup. Before each sip, you ask yourself: is there tea left? In Python, that question is the condition.

Python asks the condition before every pass, and that includes the very first one. A pass is one trip round the loop. The answer is always True or False.

Here are the five steps Python follows on every run.

FIGURE slide 3
First, check the condition. Is it True or False?
Second, if it is True, run the indented body once.
Third, update the variable the condition uses, so the value it looks at changes.
Fourth, go back and check the condition again.
Fifth, when the condition is False, leave the loop and go on to the line after it.

Why does the check come first? Because if the condition is False from the start, the body should never run. Let's test that. Suppose count is 0 and the condition is count > 0. Python checks first: is 0 greater than 0? No, that is False.

NOTE: Checking the condition
- check before each pass, even the first
- False on the first check: the body never runs
END

So the body is skipped, and Python goes straight to the line after the loop. Quick question: if count starts at 5 with the same condition, is the first check True or False?

# The update step
Think of a countdown on a phone timer. Each second, the number goes down by one. That change is the update step. In our loop, it is the line that changes the variable the condition uses.

Look at this line: count = count - 1. It takes the current value, subtracts one, and stores the answer back in count. So if count is 5, the update makes it 4.

NOTE: The update step
- count = count - 1
- takes the old value, subtracts 1, stores the new value
END

Each pass, the condition checks the new value. That is why the update matters: it moves the loop towards the point where the condition becomes False. Takeaway: the update is what lets a loop ever finish.

# Countdown program (5 to 1, then Lift off!)
Before I run it, what do you think this program prints?
CODE countdown.py
count = 5
while count > 0:
    print(count)
    count = count - 1
print("Lift off!")
END
OUTPUT
5
4
3
2
1
Lift off!
END
Look at what came out. The numbers counted down from 5 to 1, one per line, and then Lift off! appeared once the countdown was over. The count never printed 0, because the condition count > 0 became False once count reached 0. Did you predict that 0 would be left out?

Let's trace the program line by line. count starts at 5. The condition asks whether count is greater than 0. It is, so the body runs: the program prints 5, then the update makes count 4. Python goes back, checks again, and the same thing happens for 4, 3, 2 and 1.

NOTE: Tracing the countdown
- count = 5: 5 > 0 is True, print 5, count becomes 4
- count = 1: 1 > 0 is True, print 1, count becomes 0
- count = 0: 0 > 0 is False, leave the loop
END

When count reaches 0, the condition is False, so Python leaves the loop. The line print("Lift off!") is not indented, so it runs after the loop, once.

Here is the key point. The starting value, the condition and the update all work together. Change any one of them and the output changes.

# Adding 1 to 10 gives 55
Now a different problem. Suppose you want the total of the numbers 1 to 10. A loop can keep a running total for us. We need two variables: total holds the running sum, and n is the counter that goes from 1 to 10.

Here is the program. Before I run it, what do you think it prints?
CODE sum_1_to_10.py
total = 0
n = 1
while n <= 10:
    total = total + n
    n = n + 1
print("Total:", total)
END
OUTPUT
Total: 55
END
The terminal printed one line with the label Total and the number fifty-five.
NOTE:
- 0 + 1 = 1
END
That matches the sum of 1 to 10, so the program works. Let's see how it got there.

First pass: total starts at 0 and n is 1, so the body runs. Total becomes 0 plus 1, which is 1. Then n goes up to 2.

NOTE:
- 1 + 2 = 3
END
Second pass: total becomes 1 plus 2, which is 3. Then n goes up to 3.

NOTE:
- 3 + 3 = 6
END
Third pass: total becomes 3 plus 3, which is 6. The pattern carries on until n is 11. Then the condition n <= 10 is False, the loop stops, and the print line runs once with the final total.

Takeaway: a while loop can build a running total, as long as the update keeps moving the counter towards a False condition. Clear so far?

# Why a missing update gives an infinite loop
Now the update step is the reason this matters. Suppose we delete the line count = count - 1 from the countdown. The condition is still count > 0.

NOTE: Missing update
- count = 5, and nothing changes count
- 5 > 0 is True, so the body runs again
- count is still 5, so 5 > 0 is True again, and so on
END

Count never changes, so the condition never becomes False. Python keeps going round the loop for ever. The line Lift off! is never reached. Such a loop is called an infinite loop. Please don't run this one in class; it would never stop by itself.

The fix is always the update. Before you write any while loop, ask: what makes this condition False in the end? Takeaway: if the body never changes the variable in the condition, the loop never ends. Make sense?

# Recap
Let's pull it together. A while loop repeats its indented body while the condition is True. Python checks the condition before every pass, including the first, so a False start means the body never runs. The update step changes the variable the condition uses, and that is what lets the loop finish. The countdown went from 5 to 1 and then printed Lift off!. The running total of 1 to 10 gave 55. And a missing update gives an infinite loop.

# Closing
Next class we start the for loop and range(). Before then, your homework: change the countdown so it starts at 10, and see what happens. Type each program yourself, and change the numbers. Thank you, everyone.
