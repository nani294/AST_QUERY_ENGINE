def run(a, b):
    x = eval(a)
    # eval(b) in a comment is not a call
    s = "eval(b)"
    y = evaluate(b)
    return eval(s)
