import os
import pickle
from subprocess import call

password = "hunter2"
API = "x"


def load(path, mode="r"):
    data = open(path).read()
    with open(path) as f:
        text = f.read()
    return data


def risky(items, n):
    while True:
        try:
            exec(items)
        except:
            pass
        if n > 1:
            if n > 2:
                if n > 3:
                    return 1
    return 0


def walk(rows):
    for r in rows:
        for c in r:
            print(c)
    os.system("ls")
