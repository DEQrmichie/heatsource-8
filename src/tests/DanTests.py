"""Test module to spit out and check HeatSource information"""
from warnings import simplefilter

########################################
# Import the graphical user interface library, and start it up so that
# we can spit out a progress bar
import wx
app = wx.App()
app.MainLoop()
from ProgressBar import ProgressBar

#######################################
# Turn of Metta's warnings and programming comments
simplefilter('ignore', UserWarning)

datadir = "C:\\Temp\\"
outputdir = "C:\\Temp\\"

###########################################
# Import the HeatSourceInterface class and create an instance with
# the Umpqua Toketee file
from Excel.HeatSourceInterface import HeatSourceInterface
# This assumes this file exists.
# This will run the entire setup. What you have left- assuming I don't
# make it fail, will be a fully live instance

HS = HeatSourceInterface(datadir+"HS7_Jackson_CCC.xls", gauge=ProgressBar())
#HS = HeatSourceInterface("D:\\dan\\heatsource tests\\Toketee_CCC.xls", gauge=ProgressBar())


############################################

############################################
# Open a file in the windows temp directory

# Filenames are easier to change as a variable, remember to escape the
# backslashes
filename = outputdir+"boundary.out"
f = open(filename, 'w') # Open the file writable
filename2 = outputdir+"continuous.out"
g = open(filename2, 'w') # Open the file writable
filename3 = outputdir+"tributaries.out"
h = open(filename3, 'w') # Open the file writable
filename4 = outputdir+"nodes.out"
nodes_out = open(filename4, 'w') # Open the file writable


# Note that the open() function returns a class instance that is actually a file object.
# This is another example of the power of classes and Object-Orientation. If we did this
# the old way, we would have to operate on a single file at a time, at a very low level.
# With classes, we can open as many as we want, and use f.write(), f.close(), etc.

############################
# Do stuff
# At this point, it might be useful for you to comment things out of your local version of
# HeatSourceInterface()
# Go to the __initialize() method, which is called from __init__(), and start at the bottom.
# (Leave "del self.PB" alone, it just deletes the progress bar.
# I would comment out the following to start:
#
#        self.ScanMorphology()
#        self.BuildStreamNodes()
#        self.GetInflowData()
#        self.GetContinuousData()
#        map(lambda x:x.ViewToSky(),self.Reach)
#        map(lambda x:x.CalcStreamGeom(),self.Reach)
#
# Which will mean that the HS = ... line above will just run the GetBoundaryConditions()
# method. This way, you can do the following
##################
# Print out some boundary condition information from the Discharge conditions
BC = HS.BC # Get the boundary conditions class
#print BC.Q[0:5] # print first 5 elements of the boundary conditions

# temporary function that prints the attribute of a value, use as attr(object)-> object.t
#attr = lambda x: x.t

# maps a function to a list, so that the given function is called for each object in
# a list, with that object as the argument. Returns a list.
#l = map(attr,BC.Q)
#print l[0:5] # print the time attribute of the first 5 elements of the boundary conditions

# That command print the time key, which is a Python datetime object, let's print it in
# a more readable fashion. The datetime object has a method called isoformat, which prints
# the time in a human readable format. Since the lambda construct above returns x.t, and t
# is the datetime object, we can use x.t.isoformat() in the lambda construct. Lets put it all
# on one line, which is a bit less readable for the beginner, but more appropriately Pythonic,
# and how much code is written:
#print map(lambda x: x.t.isoformat()[:-6],BC.Q)[0:5]


#line = "" # Create a string

#for val in BC.Q: # Cycle through the values in the discharge boundary conditions
#    line += "%s," % `val` # Add each to the string, with a comma after it. The quotes make it taste better!

# write the values to a file, comma separated. We strip the last character from the line, because
# it prints an extra comma, and we're too lazy to take care of that in such a simple loop, above.
#f.write(line[:-1]+"\n")

# We can actually do the above in a single loop, because the BoundCond class has an __iter__() method
# which will allow us to iterate over the entire class in a single call. Let's print a line to the
# file to separate the last command from this one:
#f.write("#"*50 + "\n") # Write 50 pound signs and a newline

# Now let's iterate over the entire boundary condition class. The class's iterator returns an iterator
# over each internal list (Discharge, temperature, cloudiness) in turn.
#line = "" # Clear the line

f.write("BC.Q.t, BC.Q, BC.T, BC.C\n")
aaa = 0
#Could I use map here?  Could I get rid of count?
for val in BC.Q:
    f.write("%s,%s,%s,%s\n" % (val.t.isoformat(' ')[:-6], val, BC.T[aaa], BC.C[aaa]))
    aaa = aaa + 1

g.write("node.Wind.t,")
cont_node_list = []
for node in HS.Reach:
    if node.Humidity:
        cont_node_list.append(node)
        g.write("%s,%s,%s,%s," % (node, node, node, node))
g.write("\nnode.Wint.t,")
for node in cont_node_list:
    g.write("Wind, Humidity, T_air, T_stream,")
g.write("\n")
print cont_node_list

node1 = cont_node_list[0]
for i in node1.Wind:
    #print node, node.Humidity
    #if node.Humidity:
#    for i in node.Humidity:
    g.write("%s," % i.t.isoformat(' ')[:-6])
    for node in cont_node_list:
        g.write("%s,%s,%s,%s," % (node.Wind[i.t, 0], node.Humidity[i.t, 0], node.T_air[i.t, 0], node.T_stream[i.t, 0]))
    g.write("\n")

#print headers for node file
nodes_out.write("Node\t")
for k in HS.Reach[0].__slots__:
    nodes_out.write("%s\t" % k)
for k in HS.Reach[0].slots:
    nodes_out.write("%s\t" % k)

nodes_out.write("\n")

for node in HS.Reach:
    nodes_out.write("%s\t" % node)
    for k in node.__slots__:
        try: nodes_out.write("%s\t" % getattr(node, k))
        except: nodes_out.write("None\t")
    for k in node.slots:
        try: nodes_out.write("%s\t" % getattr(node, k))
        except: nodes_out.write("None\t")

#    import sys
#    sys.exit()
    nodes_out.write("\n")


# Started for tributary inputs but need to wait until operational!
#trib_node_list = []
#for node in HS.Reach:
#    print node, node.Q_tribs
#    if node.Q_tribs:
#        trib_node_list.append(node)
#
#print trib_node_list

#node1 = trib_node_list[0]
#for i in node1.Q_tribs:
#    h.write("%s," % i.t.isoformat(' ')[:-6])
#    for node in cont_node_list:
#        h.write("%s,%s," % (node.Q_tribs[i.t, 0], node.T_tribs[i.t, 0]))
#    h.write("\n")

#    print HS.Reach[i.km,1]

#for cond in BC:
#    for val in cond:
#        if len(line): line += "," # Add a comma at the beginning of each conditions iteration if we're not at the beginning
#        line += "%s" % `val` # add the value as a string, ignoring the comma.
#    f.write(line+"\n") # write it to the file
#    line = "" # Then reset the line for the next conditions list

# So, here we have an issue. If we look at the resulting file in the temp directory, we see that two lines
# of data were printed, but the BoundCond class holds boundary conditions for discharge, temp AND cloudiness.
# Thus, there's a problem because only two out of three lists printed. The problem is either in the BoundCond
# iterator, or in the way the lists are filled with data. At this point, the Eclipse debugger comes in handy.
# If you right (left) click over the left edge of the source code window, you can set a breakpoint. Then
# instead of RUNNING the program, you can DEBUG the program (Just like you set up the run, but choose
# "debug as.."). Set a breakpoint at the last for loop and look at the variables. You'll see that
# the BC variable has 4, not 3 attributes. They are Q, T, C and Cloudiness. Meaning that I fucked up the way
# the list is built and added the list to the BoundCond class. This is exactly the type of error that it
# would REALLY help to find now. I've left it as an illustration.


f.close() # CLOSE THE FILE!!
g.close()
h.close()
nodes_out.close()
del HS