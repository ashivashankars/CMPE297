"""Run with: python test_calc.py   (exit code 0 = all tests pass)"""
from calc import add, divide, subtract

assert add(2, 3) == 5, "add"
assert subtract(10, 4) == 6, f"subtract(10, 4) returned {subtract(10, 4)}"
assert divide(9, 3) == 3, "divide"
try:
    divide(1, 0)
    raise AssertionError("divide(1, 0) should raise ValueError('cannot divide by zero')")
except ValueError:
    pass
print("all 4 tests passed")
