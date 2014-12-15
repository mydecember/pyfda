# -*- coding: utf-8 -*-
"""
databroker.py

Created on Wed Dec 03 06:13:50 2014

http://stackoverflow.com/questions/13034496/using-global-variables-between-files-in-python
oder
http://pymotw.com/2/articles/data_persistence.html

@author: Christian Muenker
"""

# importing databroker runs the module once, defining all globals and variables
global gD
gD = {}
gD['rc'] = {'lw':1.5, 'font.size':12} # rc Params for matplotlib
gD['N_FFT'] = 2048

# Lists for dynamic imports from filter design subdirectory
gD['initFileComments'] = [] # comment lines from initFile
gD['initFileNames'] = [] # Python file names found in initFile (without .py)
gD['importModules'] = [] 
# the actual modules for import, e.g. "<module 'filterDesign.cheby1' from 
#'D:\Daten\design\python\git\pyFDA\pyFDA\filterDesign\cheby1.pyc'>
gD['importNames'] = ['cheby2', 'equiripple'] # names of filter files / classes


gD['coeffs'] = ([1,1,1],[3,0,2])
gD['zpk'] = ([-0.5 + 3**0.5/2.j, -0.5 - 3**0.5/2.j],
            [(2./3)**0.5 * 1j, -(2./3)**0.5 * 1j], 1)
            


# Dictionary describing the available combinations of response types (rt), 
# filter types (ft) and design methods (dm)
# TODO: This has to be created automatically !!!
gD['params'] = {\
    "BP":\
        {"IIR": ["butter", "cheby1", "cheby2", "ellip"],
         "FIR": ["equiripple", "firls", "window"]},
    "BS":\
        {"IIR": ["butter", "cheby1", "cheby2", "ellip"],
         "FIR": ["equiripple", "firls", "window"]},
    "LP":\
        {"IIR": ["butter", "cheby1", "cheby2", "ellip"],
         "FIR": ["equiripple", "firls", "window"]},
    "HP":\
        {"IIR": ["butter", "cheby1", "cheby2", "ellip"],
         "FIR": ["equiripple", "firls", "window"]},
    "HIL":\
        {"FIR": ["equiripple"]}
         }
# Dictionaries for translating short (initernal) names to full names
gD['rtNames'] = {"LP":"Lowpass", "HP":"Highpass", "BP":"Bandpass",
                 "BS":"Bandstop","HIL":"Hilbert"}
gD['dmNames'] = {#IIR
                  "butter":"Butterworth", "cheby1":"Chebychev 1", 
                  "cheby2":"Chebychev 2",  "ellip":"Elliptic",
                  # FIR:                  
                  "equiripple":"Equiripple", "firls":"Least-Square",
                  "window":"Windowed"}

# Dictionary containing current specifications and selections
# TODO: This has to be created automatically !!! 
#-------------------------------------- 
# Current filter selection                 
gD['curFilter'] = {"rt":"LP", "ft":"FIR", "dm":"equiripple"}
# Current filter specifications
gD['curSpecs'] = {'ord':10, 
            'A_pb':1., 'A_pb2': 1, 'F_pb':0.1, 'F_pb2':0.4,
            'A_sb':60., 'A_sb2': 60, 'F_sb':0.2, 'F_sb2':0.3,
            'W_pb':1, 'W_sb':1}

    



"""
Alternative: Use the shelve module


import shelve

### write to database:
s = shelve.open('test_shelf.db')
try:
    s['key1'] = { 'int': 10, 'float':9.5, 'string':'Sample data' }
finally:
    s.close()

### read from database:   
s = shelve.open('test_shelf.db')
# s = shelve.open('test_shelf.db', flag='r') # read-only
try:
    existing = s['key1']
finally:
    s.close()

print(existing)

### catch changes to objects, store in in-memory cache and write-back upon close
s = shelve.open('test_shelf.db', writeback=True)
try:
    print s['key1']
    s['key1']['new_value'] = 'this was not here before'
    print s['key1']
finally:
    s.close()
    
"""