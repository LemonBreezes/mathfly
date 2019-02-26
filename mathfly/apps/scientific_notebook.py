'''
Created on Sep 4, 2018

@author: Mike Roberts
'''
from dragonfly import Function, Choice, Key, Text, Mouse, IntegerRef
from dragonfly import AppContext, Grammar, Repeat

from mathfly.lib import control, utilities
from mathfly.lib.merge.mergerule import MergeRule

class SNRule(MergeRule):
    pronunciation = "scientific notebook"

    mapping = {
        "new file": Key("f10/5, down, enter"),
        "open file": Key("c-o"),
        "save file": Key("f10/5, down:5, enter"),
        "save as": Key("f10/5, down:6, enter"),
        "export document": Key("f10/5, down:8, enter"),

        "toggle math": Key("c-m"),
        "toggle text": Key("c-t"),
        "body math": Key("a-2, down, enter"),
        "body text": Key("a-2, down:2, enter"),


        "evaluate": Key("c-e"),

        }
    extras = [
        IntegerRef("n", 1, 10),

    ]
    defaults = {
        "n": 1,
    }

context = AppContext(executable="scientific notebook")
grammar = Grammar("scientific notebook", context=context)
rule = SNRule(name="scientific notebook")
grammar.add_rule(rule)
grammar.load()