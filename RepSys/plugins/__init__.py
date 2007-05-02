import os

def load():
    # based on smart's plugin system 
    pluginsdir = os.path.dirname(__file__)
    for entry in os.listdir(pluginsdir):
        if entry != "__init__.py" and entry.endswith(".py"):
            __import__("RepSys.plugins."+entry[:-3])
        elif os.path.isdir(entry):
            initfile = os.path.join(entry, "__init__.py")
            if os.path.isfile(initfile):
                __import__("RepSys.plugins."+entry)
