# Uses most of the supported subset.
def compute(a, b=2):
    total = 0
    for i in [1, 2, 3]:
        if i % 2 == 0 and not a is None:
            total = total + i * b
        elif i > 10 or a:
            continue
        else:
            break
    point = (1, 2)
    x, y = point
    values = [x, y, -total]
    try:
        total = values[0] / (b - 2)
    except ZeroDivisionError as err:
        print("div by zero", err)
    finally:
        print("done")
    return total, values
