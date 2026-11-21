def test():
    f = open("data.txt")
    with open("ok.txt") as g:
        data = g.read()
    return f
