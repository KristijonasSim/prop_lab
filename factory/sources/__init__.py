"""Where ideas come from. Each source returns a list of `spec.Strategy`.

A source never decides anything and never touches a price. It only says "here
is an idea, expressed in the grammar". Everything after that is steps 2-7.
"""
from factory.sources import invent, tradingview   # noqa: F401
