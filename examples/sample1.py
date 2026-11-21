def process(filename):
    f = open(filename)

    for item in items:
        for x in item:
            print(x)

    eval(user_input)

    try:
        risky()
    except:
        pass

    return f
